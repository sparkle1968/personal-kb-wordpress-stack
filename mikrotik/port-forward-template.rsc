# Debian VM LAN IP example. Replace this with your server's LAN IP.
# Put filter rules before final WAN input/forward drop rules if your firewall has them.

:local vmIp "10.0.0.50"
:local wanInterface "pppoe-out1"

/ip firewall nat
add chain=dstnat in-interface=$wanInterface protocol=tcp dst-port=80 action=dst-nat to-addresses=$vmIp to-ports=80 comment="home-wordpress http"
add chain=dstnat in-interface=$wanInterface protocol=tcp dst-port=443 action=dst-nat to-addresses=$vmIp to-ports=443 comment="home-wordpress https"

/ip firewall filter
add chain=forward in-interface=$wanInterface protocol=tcp dst-address=$vmIp dst-port=80,443 action=accept comment="allow home-wordpress web"
