export PATH=~/.local/bin:$PATH
cp ~/pv/in/tmh-helpers.mjs ~/pv/in/doctor.mjs ~/pv/verifier/
P=/pv/JB-0/__commit/doctor; PORT=23001; mkdir -p /tmp/doc
cd ~/pv/base/jeecgboot-vue3
pkill -f "vite --host 127.0.0.1 --port $PORT" 2>/dev/null
VITE_PUBLIC_PATH=$P/ VITE_GLOB_API_URL=$P/jeecgboot VITE_USE_MOCK=false VITE_PROXY="[[\"$P/jeecgboot\",\"http://localhost:8080/jeecg-boot\"]]" setsid nohup pnpm exec vite --host 127.0.0.1 --port $PORT --strictPort > /tmp/vite.log 2>&1 < /dev/null &
for i in $(seq 1 120); do c=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:$PORT$P/); [ "$c" = 200 ] && break; sleep 2; done; echo vite=$c after $((i*2))s
cd ~/pv/verifier && TMH_JB_YML=~/pv/base/jeecg-boot/jeecg-module-system/jeecg-system-start/src/main/resources/application-dev.yml timeout 600 node doctor.mjs http://127.0.0.1:$PORT$P/ /tmp/doc 2>&1 | tail -6
tail -3 /tmp/vite.log
