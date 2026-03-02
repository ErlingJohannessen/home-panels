python -m panel serve vehiclemap.py \
  --address 0.0.0.0 \
  --port 5010 \
  --log-level info \
  --root-path /restricted/panels \
  --allow-websocket-origin accretiosolutions.com \
  --allow-websocket-origin www.accretiosolutions.com
