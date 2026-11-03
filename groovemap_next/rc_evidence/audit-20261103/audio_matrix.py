"""Installed decoder coverage. Synthetic bytes; no model or musical quality claim."""
import json,pathlib,struct,sys,numpy as np
from groovemap_next.drum_transcriber import load_wav_mono,transcribe_drum_stem
root=pathlib.Path(sys.argv[1]);root.mkdir(exist_ok=True)
def wav(tag,channels,sr,bits,raw):
 align=channels*(bits//8)
 fmt=struct.pack('<HHIIHH',tag,channels,sr,sr*align,align,bits)
 body=b'WAVEfmt '+struct.pack('<I',16)+fmt+b'data'+struct.pack('<I',len(raw))+raw
 if len(raw)%2:body+=b'\0'
 return b'RIFF'+struct.pack('<I',len(body))+body
results=[]
for sr in (16000,44100,48000):
 for channels in (1,2):
  for bits in (8,16,24,32):
   values=[-(2**(bits-2)),0,2**(bits-2)]*channels
   if bits==8:raw=bytes(v+128 for v in values)
   else:raw=b''.join(int(v).to_bytes(bits//8,'little',signed=True) for v in values)
   p=root/f'pcm-{sr}-{channels}-{bits}.wav';p.write_bytes(wav(1,channels,sr,bits,raw))
   x,rate=load_wav_mono(p)
   expected=np.array(values,dtype=float).reshape(-1,channels).mean(1)/(2**(bits-1))
   assert rate==sr and x.shape==(3,) and np.allclose(x,expected)
   results.append({'sr':sr,'channels':channels,'bits':bits,'status':'PASS'})
  raw=np.array([.25,-.25,.5]*channels,dtype='<f4').tobytes()
  p=root/f'float-{sr}-{channels}.wav';p.write_bytes(wav(3,channels,sr,32,raw))
  x,rate=load_wav_mono(p)
  assert rate==sr and x.shape==(3,) and np.isfinite(x).all()
  results.append({'sr':sr,'channels':channels,'format':'FLOAT32','status':'PASS'})
for bad in (float('nan'),float('inf'),float('-inf')):
 p=root/'nonfinite.wav';p.write_bytes(wav(3,1,48000,32,np.array([bad],dtype='<f4').tobytes()))
 try:load_wav_mono(p)
 except ValueError:pass
 else:raise AssertionError('nonfinite accepted')
for samples in (0,10,48000):
 p=root/f'silence-{samples}.wav';p.write_bytes(wav(1,1,48000,16,b'\0\0'*samples))
 assert transcribe_drum_stem(p)==[]
p=root/'truncated.wav';p.write_bytes(wav(1,1,48000,16,b'\0'*100)[:-8])
try:load_wav_mono(p)
except ValueError:pass
else:raise AssertionError('truncation accepted')
print(json.dumps({'matrix':results,'nonfinite_rejected':3,'empty_short_silence_no_fabricated_events':True,'truncated_chunk_rejected':True,'exit_code':0},indent=2))
