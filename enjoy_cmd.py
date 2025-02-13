import wandb
import os
import json
import glob
from pyfiglet import Figlet
from termcolor import colored

### 需要手动更改项
exp_id = 206
best_n = 0  ###默认设定（一般不变）为最优模型，如需改动需要train中设置存储多个bestmodel
envid = "BounceBall_Pybullet_env-v0"
algo = "sac"
envconfig_path = os.path.join(os.path.dirname(__file__), "logs/%s/%s_%d/env_config.json"%(algo, envid, exp_id))

if not os.path.exists(envconfig_path):
    raise IOError("envconfig file does not exist. Path: %s")%envconfig_path

with open(envconfig_path) as fr:
    envconfig = json.load(fr)
    

train_computer_userName=envconfig.get("modelName_prefix",None)
task=envconfig.get("000_initBallMethod",None)
### 打印信息

f=Figlet(font='starwars',width=150)
f2=Figlet(font='slant',width=150)
logo="PeiTian Tech"
print (f.renderText("\n"))
print (colored(f.renderText(logo),"light_green"))
print (f.renderText("\n"))
print (colored(f2.renderText(envid),"light_green"))
print (f.renderText("\n"))
runname = train_computer_userName
f3=Figlet(font='standard',width=110)
print(colored(f3.renderText(str("Model ID "+runname) ),"light_yellow"))





print(">>> env_config:")
print(envconfig)

envconfig_str="config:\"%s\""%envconfig

# cmd = 'python enjoy.py --algo %s --env %s -f logs/ --exp-id %d --env-kwargs gym_render:True %s '%(algo, envid, exp_id, envconfig_str)
cmd = 'python enjoy.py --algo %s --env %s -f logs/ --exp-id %d --load-best --best-n %d --env-kwargs gym_render:True %s --task %s'%(algo, envid, exp_id, best_n, envconfig_str,task)

print(">>> enjoy command:")
print(cmd)

os.system(cmd)
