python -m panel serve home.py vehiclemap.py imageviewer.py  \
  --address 0.0.0.0 \
  --port 5010 \
  --log-level info \
  --root-path /restricted/panels \
  --index=home \
  --allow-websocket-origin accretiosolutions.com \
  --allow-websocket-origin www.accretiosolutions.com

