import wandb
import os
import json
import glob

envid = "BounceBall_Pybullet_env-v0"
algo = "sac"
exp_id = 1

logpath = os.path.join(os.path.dirname(__file__), "logs/%s/%s_%d/"%(algo, envid, exp_id))

with open(logpath+"env_config.json") as fr:
    envconfig = json.load(fr)

print(">>> env_config:")
print(envconfig)

envconfig_str="config:\"%s\""%envconfig

# cmd = 'python enjoy.py --algo %s --env %s -f logs/ --exp-id %d --env-kwargs gym_render:True %s '%(algo, envid, exp_id, envconfig_str)
cmd = 'python enjoy.py --algo %s --env %s -f logs/ --exp-id %d --load-best --best-n 0 --env-kwargs gym_render:True %s '%(algo, envid, exp_id, envconfig_str)

print(">>> enjoy command:")
print(cmd)

os.system(cmd)
