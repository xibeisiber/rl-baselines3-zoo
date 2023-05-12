import os
import json
import glob

def get_latest_run_id(log_path: str, env_name: str) -> int:
    """
    Returns the latest run number for the given log name and log path,
    by finding the greatest number in the directories.

    :param log_path: path to log folder
    :param env_name:
    :return: latest run number
    """
    max_run_id = 0
    for path in glob.glob(os.path.join(log_path, env_name + "_[0-9]*")):
        run_id = path.split("_")[-1]
        path_without_run_id = path[: -len(run_id) - 1]
        if path_without_run_id.endswith(env_name) and run_id.isdigit() and int(run_id) > max_run_id:
            max_run_id = int(run_id)
    return max_run_id

envid = "BounceBall_Pybullet_env-v0"

algo="sac"

logpath = os.path.join(os.path.dirname(__file__), "logs/%s"%algo)
run_id = get_latest_run_id(logpath, envid) + 1 

###############################################  训练时需要调整的参数
pretrain = True  # 是否需要用预训练的模型
pretrain_model_id = 28
pretrain_best_model_id = "best_model"   ###选择加载哪个bestmodel- 20230512脚本默认改为训练只有一个最佳model
pretrain_best_model_flag = True     ###True则加载最佳模型，False加载最后模型
if pretrain_best_model_flag:
    model_file = "%s.zip"%pretrain_best_model_id
else:
    model_file = "%s.zip"%envid

envconfig = {
    "00_modelname": "air4a", # "air4a", "air7l_b"
    "000_initBallMethod": "toss", # "fall", "toss", "random"
    "act_opt": 2,
    "01_frame_skip": 80,
    "02_robotobs_timelag": 22,
    "03_ballobs_timelag": 114,
    "04_act_timelag": 50,
    "05_obs_stack_n": 20,
    "07_rw_coeff_sparse": 1,
    "08_rw_coeff_paddlez": 1,
    "09_rw_coeff_ballvel": 3.5,
    "10_rw_coeff_acc": 0.01,
    "11_rw_coeff_dist": 0.01,
    "12_rw_coeff_baseballdis": 0.005,
    "rand_ballpos": 0.05,
    "rand_force_on_ball": 0.001,
    "rand_bounceforce_on_ball": 0.01,
    "13_rand_obs_ballpos": 0.01,
    "14_rand_obs_ballvel": 0.1,
    "q_alpha": 0.01,
    "q_vel_alpha": 0.01,
    "act_alpha": 1,
    "act_acc_alpha": 1
}

###############################################  end 训练时需要调整的参数


pretrain_model_file = os.path.join(os.path.dirname(__file__), "logs/%s"%algo, "%s_%d"%(envid, pretrain_model_id), model_file)

projname = "BounceBallEnv"

runname = os.getlogin()+"_"+str(run_id)

envconfig_str="config:\"%s\""%envconfig


if pretrain:
    print(">>> use pretrained model %s"%pretrain_model_file)
    if not os.path.exists(pretrain_model_file):
        raise IOError("Model %s does not exist"%pretrain_model_file)
    cmd = 'python train.py --algo %s --env %s -i %s --save-model-n 5 --wandb-project-name %s --wandb-run-name %s --env-kwargs %s --vec-env subproc --n-eval-envs 5 --eval-freq 50000 -P'%(algo, envid, pretrain_model_file, projname, runname, envconfig_str)
else:
    cmd = 'python train.py --algo %s --env %s --save-model-n 1 --wandb-project-name %s --wandb-run-name %s --env-kwargs %s --vec-env subproc --n-eval-envs 5 --eval-freq 50000 -P'%(algo, envid, projname, runname, envconfig_str)

print(">>> Train command:")
print(cmd)

os.system(cmd)
