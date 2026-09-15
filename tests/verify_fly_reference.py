"""Compare l'adaptateur au moteur original et aux données réelles de Pytorch_fly.
À lancer avec l'environnement Python de Pytorch_fly ; aucun accès au robot.
"""
import argparse
import json
from pathlib import Path
import sys
import time
import numpy as np

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('source',type=Path)
args=parser.parse_args()
sys.path.insert(0,str(root/'server/control-dashboard/fastapi-dashboard'))
sys.path.insert(0,str(args.source/'src'))
from fly_brain import FlyBrain
from flyconnectome.embodied import EmbodiedFly

brain=FlyBrain(root/'server/control-dashboard/fly-data')
assert brain.load()['status']=='ready',brain.snapshot()
report={'neurons':brain.weight.shape[0],'edges':brain.weight.nnz,'scenarios':[]}
for name,left,right,front in [('repos',False,False,False),('gauche',True,False,False),('droite',False,True,False),('avant',False,False,True)]:
    brain.reset()
    original=EmbodiedFly(brain.weight,brain.groups)
    original.sense=lambda:{'odor_L':0.,'odor_R':0.,'vision_L':4. if left or front else 0.,'vision_R':4. if right or front else 0.}
    # Les groupes olfactifs ne sont pas stimulés par les capteurs du robot.
    original.groups={**brain.groups,'odor_L':np.array([],int),'odor_R':np.array([],int)}
    latencies=[]
    for _ in range(64):
        actual=brain.tick(dict(left=left,right=right,front=front,back=False))
        reference=original.tick()
        np.testing.assert_array_equal(brain.x,original.x)
        np.testing.assert_allclose([actual['speed'],actual['turn']],[reference['speed'],reference['turn']],atol=1e-6)
        assert -45<=actual['left']<=45 and -45<=actual['right']<=45
        latencies.append(actual['compute_ms'])
    report['scenarios'].append({'name':name,'steps':64,'identical_neural_state':True,'mean_ms':round(float(np.mean(latencies)),2),'motor_speed':actual['speed'],'motor_turn':actual['turn']})
print(json.dumps(report,ensure_ascii=False,indent=2))
