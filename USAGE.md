# 训练并将环境参数自动上传到wandb
python train_cmd.py


# 训练

python train.py --algo sac --env BounceBall_Pybullet_env-v0 -P
python train.py --algo sac --env BounceBall_Pybullet_env-v0 --vec-env subproc --n-eval-envs 3 --eval-freq 5000 -P

# 超参数优化

python train.py --algo sac --env BounceBall_Pybullet_env-v0 -n 50000 -optimize --n-trials 100 --n-jobs 1 --sampler tpe --pruner median --n-evaluations 10000 --n-eval-envs 2 --verbose 0 --vec-env subproc -P

# 测试

python -m enjoy--algo sac --env BounceBall_Pybullet_env-v0 -f logs/ --exp-id 2
python enjoy.py --algo sac --env BounceBall_Pybullet_env-v0 -f logs/ --exp-id 2 --env-kwargs gym_render:True
python enjoy.py --algo sac --env BounceBall_Pybullet_env-v0 -f logs/ --exp-id 16 --load-best --best-n 0 --env-kwargs gym_render:True

# 加载旧模型继续训练
python train.py --algo sac --env BounceBallPyBullet-v0 -i ./logs/sac/BounceBallPyBullet-v0_1/best_model.zip -n 500000 --tensorboard-log ./logs/sac/BounceBallPyBullet-v0_1 --verbose 1
