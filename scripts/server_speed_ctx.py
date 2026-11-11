#!/usr/bin/env python3
# 每個請求依「server 開機後幾分鐘」和「結束時 context 長度」分組，算生成和讀提示詞的速度。用法：scripts/server_speed_ctx.py <server log>...
import re,sys,collections
# 每個請求：server 開機後幾分鐘、結束時 context 長度、生成速度、讀提示詞速度；依 (開機時間, context) 分組
B=collections.defaultdict(lambda:[0,0.0,0,0.0,0])
for fn in sys.argv[1:]:
    cur={}
    for l in open(fn,errors='ignore'):
        m=re.match(r'\s*(\d+)\.(\d+)\.\d+\.\d+ I slot print_timing: id\s+\d+ \| task (\d+) \|\s+(prompt eval|eval) time =\s+([\d.]+) ms /\s+(\d+) tokens',l)
        if m:
            t=cur.setdefault(m.group(3),{}); k='g' if m.group(4)=='eval' else 'p'
            t[k]=(int(m.group(6)),float(m.group(5))/1000); continue
        m=re.match(r'\s*(\d+)\.(\d+)\.\d+\.\d+ I slot\s+release: .*task (\d+) \| stop processing: n_tokens = (\d+)',l)
        if m and m.group(3) in cur:
            t=cur.pop(m.group(3)); up=int(m.group(1)); n=int(m.group(4))
            ub='<30' if up<30 else ('30-60' if up<60 else '>=60')
            cb='<10k' if n<10000 else '10-20k' if n<20000 else '20-30k' if n<30000 else '>=30k'
            b=B[(ub,cb)]; g=t.get('g',(0,0)); p=t.get('p',(0,0))
            if g[0]<20: continue
            b[0]+=g[0];b[1]+=g[1];b[2]+=p[0];b[3]+=p[1];b[4]+=1
for k in sorted(B):
    g,gt,p,pt,c=B[k]
    print(f"up {k[0]:>5}min ctx {k[1]:>6}: n={c:3d} gen {g/gt if gt else 0:5.1f} t/s  prompt {p/pt if pt else 0:6.1f} t/s ({p} tok)")
