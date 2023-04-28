import wandb
import os
import json
import glob

envid = "BounceBall_Pybullet_env-v0"
algo = "sac"
exp_id = 2

envconfig_path = os.path.join(os.path.dirname(__file__), "logs/%s/%s_%d/env_config.json"%(algo, envid, exp_id))

if not os.path.exists(envconfig_path):
    raise IOError("envconfig file does not exist. Path: %s")%envconfig_path

with open(envconfig_path) as fr:
    envconfig = json.load(fr)

print(">>> env_config:")
print(envconfig)

envconfig_str="config:\"%s\""%envconfig

# cmd = 'python enjoy.py --algo %s --env %s -f logs/ --exp-id %d --env-kwargs gym_render:True %s '%(algo, envid, exp_id, envconfig_str)
cmd = 'python enjoy.py --algo %s --env %s -f logs/ --exp-id %d --load-best --env-kwargs gym_render:True %s '%(algo, envid, exp_id, envconfig_str)

print(">>> enjoy command:")
print(cmd)

os.system(cmd)
