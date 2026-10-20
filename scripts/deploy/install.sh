#!/usr/bin/env bash
# 在服务器上装 Webuddy：解开部署包后，在包目录里运行  sudo bash install.sh
# 装到 /opt/webuddy（WEBUDDY_HOME 可改），起一个服务 webuddy，运维（JeecgBoot）和重构（RealWorld）两个项目都在里面。
# 平台只听本机 127.0.0.1:8790（PORT 可改），外面用域名 webuddy.bbstack.date（DOMAIN 可改）访问：
# 服务器上有 Caddy 时不碰 nginx，最后打印要加进 Caddyfile 的一段；没有 Caddy 时装 nginx 转发。
# 访问要带令牌；令牌在 /etc/webuddy.env，安装时随机生成，重装不变。
# 自动处理默认关着（不会一启动就调用智能体花额度），要用时在页面「设置」里打开。
# GitHub 在服务器上慢或连不上时，可以换镜像：JEECG_GIT=... RW_GIT=... sudo -E bash install.sh
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
H=${WEBUDDY_HOME:-/opt/webuddy}
PORT=${PORT:-8790}; DOMAIN=${DOMAIN:-webuddy.bbstack.date}
JEECG_GIT=${JEECG_GIT:-https://github.com/jeecgboot/JeecgBoot.git}
RW_GIT=${RW_GIT:-https://github.com/gothinkster/aspnetcore-realworld-example-app.git}
RW_SRC=a51468ca042605d22f7c78082e5d6129c1b995c6
RUN_AS=${SUDO_USER:-$(id -un)}

need() { command -v "$1" >/dev/null || { echo "缺少 $1，请先安装（Ubuntu: apt install $2；CentOS: yum install $2）"; exit 1; }; }
need python3 python3; need git git; need ssh openssh-client; need curl curl
python3 -c 'import sys; sys.exit(sys.version_info < (3, 8))' || { echo "需要 Python 3.8 以上"; exit 1; }
[ "$(id -u)" = 0 ] || { echo "请用 sudo 运行"; exit 1; }

if ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$PORT\$" && ! systemctl is-active -q webuddy 2>/dev/null; then
  echo "端口 $PORT 已经被别的程序占用，换一个：PORT=8795 sudo -E bash install.sh"; exit 1
fi

echo "== 装到 $H（服务以 $RUN_AS 身份运行）"
mkdir -p "$H/data" "$H/repos"
rm -rf "$H/app"; cp -r "$HERE/app" "$H/app"
if [ -e "$H/data/platform.db" ]; then echo "  $H/data 已有数据，保留不覆盖"; else cp -r "$HERE/data/." "$H/data/"; fi

clone() {  # <地址> <目录>
  if [ -d "$2/.git" ]; then echo "  $2 已存在"; return; fi
  echo "  克隆 $1（JeecgBoot 较大，要等几分钟）"; git clone -q "$1" "$2"
}
echo "== 项目代码"
clone "$JEECG_GIT" "$H/repos/JeecgBoot"
if [ -s "$HERE/repos/JeecgBoot-tmh.bundle" ]; then
  git -C "$H/repos/JeecgBoot" fetch -q "$HERE/repos/JeecgBoot-tmh.bundle" 'refs/heads/*:refs/heads/*' 2>/dev/null \
    && echo "  智能体改出来的分支已导入" || echo "  （改动分支没导入，不影响查看平台里记的改动）"
fi
git -C "$H/repos/JeecgBoot" checkout -q -f "$(cat "$HERE/repos/JeecgBoot.head")" 2>/dev/null || true
rm -rf "$H/repos/JeecgBoot/.tmh"; tar -C "$H/repos/JeecgBoot" -xzf "$HERE/repos/JeecgBoot.tmh.tgz"
clone "$RW_GIT" "$H/repos/realworld-net"
git -C "$H/repos/realworld-net" checkout -q -B tmh-test "$RW_SRC"
rm -rf "$H/repos/realworld-net/.tmh"; tar -C "$H/repos/realworld-net" -xzf "$HERE/repos/realworld-net.tmh.tgz"
mv "$H/repos/realworld-net/tmh" "$H/repos/realworld-net/.tmh"

echo "== 数据里的项目路径改成服务器上的"
python3 - "$H" <<'PY'
import json, sqlite3, sys
h = sys.argv[1]
c = sqlite3.connect("%s/data/platform.db" % h)
for key, root in (("JB", "JeecgBoot"), ("RW", "realworld-net")):
    c.execute("UPDATE projects SET root=? WHERE key=?", ("%s/repos/%s" % (h, root), key))
c.commit(); c.close()
f = "%s/data/autoflow.json" % h
try:
    a = json.load(open(f, encoding="utf-8"))
except (OSError, ValueError):
    a = {}
a["on"] = False
json.dump(a, open(f, "w", encoding="utf-8"), ensure_ascii=False)
PY
chown -R "$RUN_AS" "$H"

echo "== 令牌和服务"
if [ ! -f /etc/webuddy.env ]; then
  printf 'TMH_TOKEN=%s\nTMH_BRAND=Webuddy\n' "$(python3 -c 'import secrets;print(secrets.token_hex(16))')" > /etc/webuddy.env
  chmod 600 /etc/webuddy.env; chown "$RUN_AS" /etc/webuddy.env
fi
HOMEDIR=$(getent passwd "$RUN_AS" | cut -d: -f6)
CODEX=$(sudo -u "$RUN_AS" -i bash -lc 'command -v codex' 2>/dev/null || true)
PATHS="$(dirname "${CODEX:-/usr/local/bin/codex}"):$HOMEDIR/.local/bin:$HOMEDIR/.npm-global/bin:/usr/local/bin:/usr/bin:/bin"
[ -n "$CODEX" ] || echo "  注意：$RUN_AS 的环境里还没有 codex 命令。先装好 Codex，再 sudo systemctl restart webuddy"
for old in webuddy-ops webuddy-reform; do  # 早先分成两个服务装过的，合成一个后停掉
  if [ -f "/etc/systemd/system/$old.service" ]; then systemctl disable -q --now "$old" || true; rm -f "/etc/systemd/system/$old.service"; fi
done
cat > /etc/systemd/system/webuddy.service <<UNIT
[Unit]
Description=Webuddy
After=network-online.target

[Service]
User=$RUN_AS
WorkingDirectory=$H/app
EnvironmentFile=/etc/webuddy.env
Environment=HOME=$HOMEDIR
Environment=PATH=$PATHS
ExecStart=/usr/bin/env python3 -m tmh serve --host 127.0.0.1 --port $PORT --data $H/data
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable -q --now webuddy
systemctl restart webuddy
sleep 3
. /etc/webuddy.env
code=$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/?token=$TMH_TOKEN" || true)
echo "  平台：$([ "$code" = 200 ] && echo 已启动 || echo "没起来（journalctl -u webuddy -n 50 看原因）")"

if command -v caddy >/dev/null || systemctl is-active -q caddy 2>/dev/null; then
  # 这台机器的网关是 Caddy，还在给别的站点用：不装 nginx，也不自动改 Caddyfile，由你加一段后检查再生效
  cat <<DONE

平台装好了（只听本机 127.0.0.1:$PORT）。这台服务器用 Caddy 做网关，域名要你在 Caddyfile 里加一段：
  1. 改之前先确认现有站点都能打开。
  2. 在 /etc/caddy/Caddyfile 末尾加上：

$DOMAIN {
    reverse_proxy 127.0.0.1:$PORT
}

  3. sudo caddy validate --config /etc/caddy/Caddyfile   通过后再  sudo systemctl reload caddy
  4. 再确认一遍原来的站点都能打开。Caddy 会自己申请 HTTPS 证书，不用 certbot。
然后浏览器打开（第一次带上令牌，之后浏览器会记住）：
  https://$DOMAIN/?token=$TMH_TOKEN
令牌在 /etc/webuddy.env，不要发到群里。
测试机：平台用 $RUN_AS 的 ssh 密钥登录测试机（auntu@43.153.76.85 -p 12022）。
  在服务器上用 $RUN_AS 身份执行一次 ssh -p 12022 auntu@43.153.76.85 echo ok 能通，构建测试才能用。
DONE
  exit 0
fi

echo "== 域名 $DOMAIN（nginx 转到本机 $PORT）"
if ! command -v nginx >/dev/null; then
  if command -v apt-get >/dev/null; then apt-get install -y -q nginx >/dev/null || true
  elif command -v yum >/dev/null; then yum install -y -q nginx >/dev/null || true; fi
fi
if command -v nginx >/dev/null; then
  if [ -d /etc/nginx/sites-available ]; then SITE=/etc/nginx/sites-available/webuddy; else SITE=/etc/nginx/conf.d/webuddy.conf; fi
  if [ -f "$SITE" ] && grep -q 'ssl_certificate' "$SITE"; then
    echo "  $SITE 已经配过证书，保留不动"
  else
    cat > "$SITE" <<NGINX
server {
    listen 80;
    server_name $DOMAIN;
    client_max_body_size 50m;
    location / {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_set_header Host 127.0.0.1;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }
}
NGINX
  fi
  [ -d /etc/nginx/sites-enabled ] && ln -sf "$SITE" /etc/nginx/sites-enabled/webuddy
  systemctl enable -q nginx 2>/dev/null || true
  if nginx -t 2>/dev/null; then (systemctl reload nginx 2>/dev/null || systemctl start nginx); echo "  nginx 已配好：$SITE"
  else echo "  nginx 配置没通过检查（sudo nginx -t 看原因），平台本身不受影响"; fi
else
  echo "  没装上 nginx，请先装好 nginx 再重跑本脚本"
fi
cat <<DONE

装好了。还剩三步要你来做：
  1. 域名解析：给 $DOMAIN 加一条 A 记录，指向这台服务器的公网 IP。
  2. 腾讯云安全组放行 TCP 80 和 443（平台的 $PORT 端口不用放行，只给 nginx 用）。
  3. 解析生效后上 HTTPS：sudo apt install certbot python3-certbot-nginx（CentOS 用 yum），
     再 sudo certbot --nginx -d $DOMAIN ，按提示填邮箱，证书会自动续期。
然后浏览器打开（第一次带上令牌，之后浏览器会记住）：
  https://$DOMAIN/?token=$TMH_TOKEN
令牌在 /etc/webuddy.env，不要发到群里。
测试机：平台用 $RUN_AS 的 ssh 密钥登录测试机（auntu@43.153.76.85 -p 12022）。
  在服务器上用 $RUN_AS 身份执行一次 ssh -p 12022 auntu@43.153.76.85 echo ok 能通，构建测试才能用。
DONE
