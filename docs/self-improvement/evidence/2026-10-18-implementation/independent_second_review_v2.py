"""Independent review: disposable localhost servers and databases only."""
import argparse, hashlib, http.client, json, re, sqlite3, tempfile, threading
from pathlib import Path
from urllib.parse import urlencode

parser=argparse.ArgumentParser()
parser.add_argument('--app',required=True)
parser.add_argument('--output',required=True)
args=parser.parse_args()
source=Path(args.app).read_bytes()
namespace={'__name__':'bounded_review_app','__file__':args.app}
exec(compile(source,args.app,'exec'),namespace)
report={'app':args.app,'source_sha256':hashlib.sha256(source).hexdigest(),'checks':[],'scope':'TemporaryDirectory and ephemeral loopback servers only'}
def check(name,condition,detail=None):
    report['checks'].append({'name':name,'passed':bool(condition),'detail':detail})
    if not condition: raise AssertionError((name,detail))
try:
  with tempfile.TemporaryDirectory(prefix='webuddy-assess-bounded-') as directory:
    for i,prefix in enumerate(('', '/demo', '/pv/BOOTV2/__commit/'+'a'*40)):
      dbpath=Path(directory)/f'{i}.db'
      server=namespace['make_server'](('127.0.0.1',0),dbpath,prefix,'独立只读复核')
      thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':0.01},daemon=True)
      thread.start()
      def call(method,path,payload=None,declared=None):
        conn=http.client.HTTPConnection('127.0.0.1',server.server_address[1],timeout=2)
        try:
          if declared is not None:
            conn.putrequest(method,path)
            conn.putheader('Content-Type','application/x-www-form-urlencoded')
            conn.putheader('Content-Length',str(declared))
            conn.endheaders(payload)
          else:
            conn.request(method,path,payload,{'Content-Type':'application/x-www-form-urlencoded'})
          response=conn.getresponse()
          status,headers,body=response.status,dict(response.getheaders()),response.read().decode('utf-8')
          return status,headers,body
        finally:conn.close()
      def rows():
        conn=sqlite3.connect(dbpath)
        try:return conn.execute('SELECT id,title,done FROM items ORDER BY id').fetchall()
        finally:conn.close()
      try:
        _,_,body=call('GET',prefix+'/')
        csrf=re.search(r'name="csrf" value="([^"]+)"',body)[1]
        for title in ('原始标题','不可改动的另一项'):
          check(prefix+' create baseline',call('POST',prefix+'/items',urlencode({'csrf':csrf,'title':title}).encode())[0]==303)
        call('POST',prefix+'/items/1',urlencode({'csrf':csrf,'done':'1'}).encode())
        before=rows()
        edit=prefix+'/items/1/edit'
        for bad in ('%FF','%E4%B8','%C0%AF','%ED%A0%80'):
          for path in (edit,prefix+'/items'):
            status,_,_=call('POST',path,('csrf='+csrf+'&title='+bad).encode())
            check(prefix+' malformed UTF-8 rejected '+path+' '+bad,status==400,status)
            check(prefix+' malformed UTF-8 cannot alter rows '+bad,rows()==before,rows())
        for length in (8192,65536):
          payload=('csrf='+csrf+'&title=%FF&padding=').encode()
          payload+=b'x'*(length-len(payload))
          status,_,_=call('POST',edit,payload)
          check(prefix+' malformed UTF-8 within recovery window '+str(length),status==400,status)
          check(prefix+' malformed window cannot alter rows',rows()==before)
        replacement='合法替换字符 � 中文'
        status,_,_=call('POST',edit,urlencode({'csrf':csrf,'title':replacement}).encode())
        check(prefix+' literal replacement character is valid text',status==303 and rows()==[(1,replacement,1),before[1]],rows())
        valid_before=rows()
        title='字'*1000
        payload=urlencode({'csrf':csrf,'title':title}).encode()
        status,_,body=call('POST',edit,payload)
        check(prefix+' complete 1000 Chinese character recovery',status==413 and title in body and rows()==valid_before,{'status':status,'bytes':len(payload)})
        status,headers,body=call('POST',edit,declared=65537)
        check(prefix+' over window rejected before request body',status==413 and headers.get('Connection')=='close' and '正文未接收' in body and rows()==valid_before,{'status':status,'connection':headers.get('Connection')})
      finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
  check('candidate source unchanged',Path(args.app).read_bytes()==source)
  report['passed']=True
finally:
  report['checks_total']=len(report['checks'])
  report['checks_passed']=sum(item['passed'] for item in report['checks'])
  Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
  print(json.dumps({k:v for k,v in report.items() if k!='checks'},ensure_ascii=False))
