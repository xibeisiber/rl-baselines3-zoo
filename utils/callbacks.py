import os
import tempfile
import time
from copy import deepcopy
from functools import wraps
from threading import Thread
from typing import Any, Callable, Dict, List, Optional, Union
import gym
import numpy as np
import datetime
import shutil

import optuna
from sb3_contrib import TQC
from stable_baselines3 import SAC
from stable_baselines3.common.callbacks import BaseCallback, EvalCallback, EventCallback
from stable_baselines3.common.logger import TensorBoardOutputFormat
from stable_baselines3.common.vec_env import VecEnv, sync_envs_normalization
from stable_baselines3.common.evaluation import evaluate_policy


class TrialEvalCallback(EvalCallback):
    """
    Callback used for evaluating and reporting a trial.
    """

    def __init__(
        self,
        eval_env: VecEnv,
        trial: optuna.Trial,
        n_eval_episodes: int = 5,
        eval_freq: int = 10000,
        deterministic: bool = True,
        verbose: int = 0,
        best_model_save_path: Optional[str] = None,
        log_path: Optional[str] = None,
    ):

        super().__init__(
            eval_env=eval_env,
            n_eval_episodes=n_eval_episodes,
            eval_freq=eval_freq,
            deterministic=deterministic,
            verbose=verbose,
            best_model_save_path=best_model_save_path,
            log_path=log_path,
        )
        self.trial = trial
        self.eval_idx = 0
        self.is_pruned = False

    def _on_step(self) -> bool:
        if self.eval_freq > 0 and self.n_calls % self.eval_freq == 0:
            super()._on_step()
            self.eval_idx += 1
            # report best or report current ?
            # report num_timesteps or elasped time ?
            self.trial.report(self.last_mean_reward, self.eval_idx)
            # Prune trial if need
            if self.trial.should_prune():
                self.is_pruned = True
                return False
        return True


class SaveVecNormalizeCallback(BaseCallback):
    """
    Callback for saving a VecNormalize wrapper every ``save_freq`` steps

    :param save_freq: (int)
    :param save_path: (str) Path to the folder where ``VecNormalize`` will be saved, as ``vecnormalize.pkl``
    :param name_prefix: (str) Common prefix to the saved ``VecNormalize``, if None (default)
        only one file will be kept.
    """

    def __init__(self, save_freq: int, save_path: str, name_prefix: Optional[str] = None, verbose: int = 0):
        super().__init__(verbose)
        self.save_freq = save_freq
        self.save_path = save_path
        self.name_prefix = name_prefix

    def _init_callback(self) -> None:
        # Create folder if needed
        if self.save_path is not None:
            os.makedirs(self.save_path, exist_ok=True)

    def _on_step(self) -> bool:
        if self.n_calls % self.save_freq == 0:
            if self.name_prefix is not None:
                path = os.path.join(self.save_path, f"{self.name_prefix}_{self.num_timesteps}_steps.pkl")
            else:
                path = os.path.join(self.save_path, "vecnormalize_tmp.pkl")

            if self.model.get_vec_normalize_env() is not None:
                self.model.get_vec_normalize_env().save(path)
                if self.verbose > 1:
                    print(f"Saving VecNormalize to {path}")
        return True


class ParallelTrainCallback(BaseCallback):
    """
    Callback to explore (collect experience) and train (do gradient steps)
    at the same time using two separate threads.
    Normally used with off-policy algorithms and `train_freq=(1, "episode")`.

    TODO:
    - blocking mode: wait for the model to finish updating the policy before collecting new experience
        at the end of a rollout
    - force sync mode: stop training to update to the latest policy for collecting
        new experience

    :param gradient_steps: Number of gradient steps to do before
        sending the new policy
    :param verbose: Verbosity level
    :param sleep_time: Limit the fps in the thread collecting experience.
    """

    def __init__(self, gradient_steps: int = 100, verbose: int = 0, sleep_time: float = 0.0):
        super().__init__(verbose)
        self.batch_size = 0
        self._model_ready = True
        self._model = None
        self.gradient_steps = gradient_steps
        self.process = None
        self.model_class = None
        self.sleep_time = sleep_time

    def _init_callback(self) -> None:
        temp_file = tempfile.TemporaryFile()

        # Windows TemporaryFile is not a io Buffer
        # we save the model in the logs/ folder
        if os.name == "nt":
            temp_file = os.path.join("logs", "model_tmp.zip")

        self.model.save(temp_file)

        # TODO: add support for other algorithms
        for model_class in [SAC, TQC]:
            if isinstance(self.model, model_class):
                self.model_class = model_class
                break

        assert self.model_class is not None, f"{self.model} is not supported for parallel training"
        self._model = self.model_class.load(temp_file)

        self.batch_size = self._model.batch_size

        # Disable train method
        def patch_train(function):
            @wraps(function)
            def wrapper(*args, **kwargs):
                return

            return wrapper

        # Add logger for parallel training
        self._model.set_logger(self.model.logger)
        self.model.train = patch_train(self.model.train)

        # Hack: Re-add correct values at save time
        def patch_save(function):
            @wraps(function)
            def wrapper(*args, **kwargs):
                return self._model.save(*args, **kwargs)

            return wrapper

        self.model.save = patch_save(self.model.save)

    def train(self) -> None:
        self._model_ready = False

        self.process = Thread(target=self._train_thread, daemon=True)
        self.process.start()

    def _train_thread(self) -> None:
        self._model.train(gradient_steps=self.gradient_steps, batch_size=self.batch_size)
        self._model_ready = True

    def _on_step(self) -> bool:
        if self.sleep_time > 0:
            time.sleep(self.sleep_time)
        return True

    def _on_rollout_end(self) -> None:
        if self._model_ready:
            self._model.replay_buffer = deepcopy(self.model.replay_buffer)
            self.model.set_parameters(deepcopy(self._model.get_parameters()))
            self.model.actor = self.model.policy.actor
            if self.num_timesteps >= self._model.learning_starts:
                self.train()
            # Do not wait for the training loop to finish
            # self.process.join()

    def _on_training_end(self) -> None:
        # Wait for the thread to terminate
        if self.process is not None:
            if self.verbose > 0:
                print("Waiting for training thread to terminate")
            self.process.join()


class RawStatisticsCallback(BaseCallback):
    """
    Callback used for logging raw episode data (return and episode length).
    """

    def __init__(self, verbose=0):
        super().__init__(verbose)
        # Custom counter to reports stats
        # (and avoid reporting multiple values for the same step)
        self._timesteps_counter = 0
        self._tensorboard_writer = None

    def _init_callback(self) -> None:
        # Retrieve tensorboard writer to not flood the logger output
        for out_format in self.logger.output_formats:
            if isinstance(out_format, TensorBoardOutputFormat):
                self._tensorboard_writer = out_format
        assert self._tensorboard_writer is not None, "You must activate tensorboard logging when using RawStatisticsCallback"

    def _on_step(self) -> bool:
        for info in self.locals["infos"]:
            if "episode" in info:
                logger_dict = {
                    "raw/rollouts/episodic_return": info["episode"]["r"],
                    "raw/rollouts/episodic_length": info["episode"]["l"],
                }
                exclude_dict = {key: None for key in logger_dict.keys()}
                self._timesteps_counter += info["episode"]["l"]
                self._tensorboard_writer.write(logger_dict, exclude_dict, self._timesteps_counter)

        return True

class EvalMultiBestCallback(EventCallback):
    """
    !!!!!! modified from EvalCallback to save several best models

    Callback for evaluating an agent.

    .. warning::

      When using multiple environments, each call to  ``env.step()``
      will effectively correspond to ``n_envs`` steps.
      To account for that, you can use ``eval_freq = max(eval_freq // n_envs, 1)``

    :param eval_env: The environment used for initialization
    :param callback_on_new_best: Callback to trigger
        when there is a new best model according to the ``mean_reward``
    :param callback_after_eval: Callback to trigger after every evaluation
    :param n_eval_episodes: The number of episodes to test the agent
    :param eval_freq: Evaluate the agent every ``eval_freq`` call of the callback.
    :param log_path: Path to a folder where the evaluations (``evaluations.npz``)
        will be saved. It will be updated at each evaluation.
    :param best_model_save_path: Path to a folder where the best model
        according to performance on the eval env will be saved.
    :param deterministic: Whether the evaluation should
        use a stochastic or deterministic actions.
    :param render: Whether to render or not the environment during evaluation
    :param verbose:
    :param warn: Passed to ``evaluate_policy`` (warns if ``eval_env`` has not been
        wrapped with a Monitor wrapper)
    """

    def __init__(
        self,
        eval_env: Union[gym.Env, VecEnv],
        callback_on_new_best: Optional[BaseCallback] = None,
        callback_after_eval: Optional[BaseCallback] = None,
        n_eval_episodes: int = 5,
        eval_freq: int = 10000,
        log_path: Optional[str] = None,
        best_model_save_path: Optional[str] = None,
        deterministic: bool = True,
        render: bool = False,
        verbose: int = 1,
        warn: bool = True,
        save_model_n: int = 5,
        params_path: Optional[str] = None,
    ):
        super().__init__(callback_after_eval, verbose=verbose)

        self.callback_on_new_best = callback_on_new_best
        if self.callback_on_new_best is not None:
            # Give access to the parent
            self.callback_on_new_best.parent = self

        self.n_eval_episodes = n_eval_episodes
        self.eval_freq = eval_freq
        self.save_model_n = save_model_n
        self.best_mean_reward_arr = np.zeros([self.save_model_n, 3])
        self.best_mean_reward_arr[:,0] = np.array(range(self.save_model_n))
        self.best_mean_reward_arr[:,1] = np.array([-np.inf]*self.save_model_n)
        self.best_mean_reward_arr[:,2] = np.array([-1]*self.save_model_n)
        self.deterministic = deterministic
        self.render = render
        self.warn = warn
        self.params_path = params_path

        # Convert to VecEnv for consistency
        if not isinstance(eval_env, VecEnv):
            eval_env = DummyVecEnv([lambda: eval_env])

        self.eval_env = eval_env
        self.best_model_save_path = best_model_save_path
        # Logs will be written in ``evaluations.npz``
        if log_path is not None:
            log_path = os.path.join(log_path, "evaluations")
        self.log_path = log_path
        self.evaluations_results = []
        self.evaluations_timesteps = []
        self.evaluations_length = []
        # For computing success rate
        self._is_success_buffer = []
        self.evaluations_successes = []

    def _init_callback(self) -> None:
        # Does not work in some corner cases, where the wrapper is not the same
        if not isinstance(self.training_env, type(self.eval_env)):
            warnings.warn("Training and eval env are not of the same type" f"{self.training_env} != {self.eval_env}")

        # Create folders if needed
        if self.best_model_save_path is not None:
            os.makedirs(self.best_model_save_path, exist_ok=True)
        if self.log_path is not None:
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

        # Init callback called on new best model
        if self.callback_on_new_best is not None:
            self.callback_on_new_best.init_callback(self.model)

    def _log_success_callback(self, locals_: Dict[str, Any], globals_: Dict[str, Any]) -> None:
        """
        Callback passed to the  ``evaluate_policy`` function
        in order to log the success rate (when applicable),
        for instance when using HER.

        :param locals_:
        :param globals_:
        """
        info = locals_["info"]

        if locals_["done"]:
            maybe_is_success = info.get("is_success")
            if maybe_is_success is not None:
                self._is_success_buffer.append(maybe_is_success)

    def _on_step(self) -> bool:

        continue_training = True

        if self.eval_freq > 0 and self.n_calls % self.eval_freq == 0:

            # Sync training and eval env if there is VecNormalize
            if self.model.get_vec_normalize_env() is not None:
                try:
                    sync_envs_normalization(self.training_env, self.eval_env)
                except AttributeError as e:
                    raise AssertionError(
                        "Training and eval env are not wrapped the same way, "
                        "see https://stable-baselines3.readthedocs.io/en/master/guide/callbacks.html#evalcallback "
                        "and warning above."
                    ) from e

            # Reset success rate buffer
            self._is_success_buffer = []

            episode_rewards, episode_lengths = evaluate_policy(
                self.model,
                self.eval_env,
                n_eval_episodes=self.n_eval_episodes,
                render=self.render,
                deterministic=self.deterministic,
                return_episode_rewards=True,
                warn=self.warn,
                callback=self._log_success_callback,
            )

            if self.log_path is not None:
                self.evaluations_timesteps.append(self.num_timesteps)
                self.evaluations_results.append(episode_rewards)
                self.evaluations_length.append(episode_lengths)

                kwargs = {}
                # Save success log if present
                if len(self._is_success_buffer) > 0:
                    self.evaluations_successes.append(self._is_success_buffer)
                    kwargs = dict(successes=self.evaluations_successes)

                np.savez(
                    self.log_path,
                    timesteps=self.evaluations_timesteps,
                    results=self.evaluations_results,
                    ep_lengths=self.evaluations_length,
                    **kwargs,
                )

            mean_reward, std_reward = np.mean(episode_rewards), np.std(episode_rewards)
            mean_ep_length, std_ep_length = np.mean(episode_lengths), np.std(episode_lengths)

            if self.verbose > 0:
                print(f"Eval num_timesteps={self.num_timesteps}, " f"episode_reward={mean_reward:.2f} +/- {std_reward:.2f}")
                print(f"Episode length: {mean_ep_length:.2f} +/- {std_ep_length:.2f}")
            # Add to current Logger
            self.logger.record("eval/mean_reward", float(mean_reward))
            self.logger.record("eval/mean_ep_length", mean_ep_length)

            if len(self._is_success_buffer) > 0:
                success_rate = np.mean(self._is_success_buffer)
                if self.verbose > 0:
                    print(f"Success rate: {100 * success_rate:.2f}%")
                self.logger.record("eval/success_rate", success_rate)

            # Dump log so the evaluation results are printed with the correct timestep
            self.logger.record("time/total_timesteps", self.num_timesteps, exclude="tensorboard")
            self.logger.dump(self.num_timesteps)

            saved_minreward_id = np.argmin(self.best_mean_reward_arr[:, 1])
            saved_minreward = self.best_mean_reward_arr[saved_minreward_id, 1]
            if mean_reward > saved_minreward:
                if self.verbose > 0:
                    print("New best mean reward!")
                self.best_mean_reward_arr[saved_minreward_id, 1] = mean_reward
                self.best_mean_reward_arr[saved_minreward_id, 2] = float(datetime.datetime.now().strftime("%Y%m%d.%H%M%S"))
                if self.best_model_save_path is not None:
                    if saved_minreward_id==0:
                        self.model.save(os.path.join(self.best_model_save_path, "best_model"))
                    else:
                        self.model.save(os.path.join(self.best_model_save_path, "best_model%d"%(saved_minreward_id)))
                    np.savetxt(os.path.join(self.best_model_save_path, "best_model_rewards.txt"), self.best_mean_reward_arr, fmt="%d  %.4f  %.6f")
                # Trigger callback on new best model, if needed
                if self.callback_on_new_best is not None:
                    continue_training = self.callback_on_new_best.on_step()
                    if saved_minreward_id==0:
                        shutil.move(os.path.join(self.params_path, "vecnormalize_tmp.pkl"), os.path.join(self.params_path, "vecnormalize.pkl"))
                    else:
                        shutil.move(os.path.join(self.params_path, "vecnormalize_tmp.pkl"), os.path.join(self.params_path, "vecnormalize%d.pkl"%saved_minreward_id))

            # Trigger callback after every evaluation, if needed
            if self.callback is not None:
                continue_training = continue_training and self._on_event()

        return continue_training

    def update_child_locals(self, locals_: Dict[str, Any]) -> None:
        """
        Update the references to the local variables.

        :param locals_: the local variables during rollout collection
        """
        if self.callback:
            self.callback.update_locals(locals_)