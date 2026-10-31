#!/bin/bash
# Rodar no root@pve — NAT imediato da rede SUAP (modelo SEI).
set -euo pipefail
echo 1 > /proc/sys/net/ipv4/ip_forward
iptables -t nat -C POSTROUTING -s 192.168.110.0/24 -o vmbr0 -j MASQUERADE 2>/dev/null \
  || iptables -t nat -A POSTROUTING -s 192.168.110.0/24 -o vmbr0 -j MASQUERADE
echo "ip_forward=$(cat /proc/sys/net/ipv4/ip_forward)"
iptables -t nat -S POSTROUTING | grep 192.168.110 || true
echo
echo "Persistir: em /etc/network/interfaces, dentro do bloco 'iface vmbr1 inet static', acrescente:"
echo "  post-up   echo 1 > /proc/sys/net/ipv4/ip_forward"
echo "  post-up   iptables -t nat -A POSTROUTING -s '192.168.110.0/24' -o vmbr0 -j MASQUERADE"
echo "  post-down iptables -t nat -D POSTROUTING -s '192.168.110.0/24' -o vmbr0 -j MASQUERADE"
