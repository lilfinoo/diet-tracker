FROM grafana/alloy:v1.10.0

COPY config.alloy /etc/alloy/config.alloy

CMD ["run", "--storage.path=/var/lib/alloy/data", "/etc/alloy/config.alloy"]
