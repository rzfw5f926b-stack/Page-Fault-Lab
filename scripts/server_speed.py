#!/usr/bin/env python3
import re,sys,collections
# 把 llama-server 的 log 依 server 開機後的時間，每 30 分鐘加總生成和讀提示詞的速度。用法：scripts/server_speed.py <server log>
b=collections.defaultdict(lambda:[0,0.0,0,0.0])
for l in open(sys.argv[1]):
    m=re.match(r'\s*(\d+)\.\d+\.\d+\.\d+ I slot print_timing.*\|\s+(prompt eval|eval) time =\s+([\d.]+) ms /\s+(\d+) tokens',l)
    if not m: continue
    h=int(m.group(1))//30; k=0 if m.group(2)=='eval' else 2
    b[h][k]+=int(m.group(4)); b[h][k+1]+=float(m.group(3))/1000
for h in sorted(b):
    g,gt,p,pt=b[h]
    print(f"{h*30:4d}-{h*30+30}min gen {g:6d} tok {g/gt if gt else 0:5.1f} t/s | prompt {p:6d} tok {p/pt if pt else 0:6.1f} t/s")
