import wandb
import os
import json
import glob
from pyfiglet import Figlet


### 需要手动更改项
exp_id = 32
best_n = 0  ###默认设定（一般不变），如需改动需要train中设置存储多个bestmodel

### 打印信息
envid = "BounceBall_Pybullet_env-v0"
algo = "sac"
f=Figlet(font='starwars',width=150)
f2=Figlet(font='slant',width=150)
logo="PeiTian Tech"
print (f.renderText(logo))
print (f.renderText("\n"))
print (f2.renderText(envid))
print (f.renderText("\n"))
runname = os.getlogin()+"_"+str(exp_id)
f3=Figlet(font='standard',width=110)
print(f3.renderText(str("Model id "+runname) ))


envconfig_path = os.path.join(os.path.dirname(__file__), "logs/%s/%s_%d/env_config.json"%(algo, envid, exp_id))

if not os.path.exists(envconfig_path):
    raise IOError("envconfig file does not exist. Path: %s")%envconfig_path

with open(envconfig_path) as fr:
    envconfig = json.load(fr)

print(">>> env_config:")
print(envconfig)

envconfig_str="config:\"%s\""%envconfig

# cmd = 'python enjoy.py --algo %s --env %s -f logs/ --exp-id %d --env-kwargs gym_render:True %s '%(algo, envid, exp_id, envconfig_str)
cmd = 'python enjoy.py --algo %s --env %s -f logs/ --exp-id %d --load-best --best-n %d --env-kwargs gym_render:False %s '%(algo, envid, exp_id, best_n, envconfig_str)

print(">>> enjoy command:")
print(cmd)

os.system(cmd)
