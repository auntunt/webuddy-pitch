"""Display instants in China time while preserving server timestamp contracts."""
TIME_JS = r"""
function serverDate(value){
  if(value instanceof Date)return value;
  let text=String(value||'').replace(' ','T');
  if(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(text))text+=(S.meta?.timestamp_offset||'+00:00');
  return new Date(text);
}
function chinaTime(value){
  if(value==null||value==='')return '';
  if(!(value instanceof Date)&&!(typeof value==='string'&&/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}/.test(value)))return value;
  const date=serverDate(value);if(!Number.isFinite(date.getTime()))return String(value);
  const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).formatToParts(date);
  const p=Object.fromEntries(parts.map(x=>[x.type,x.value]));return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}:${p.second}`;
}
"""
