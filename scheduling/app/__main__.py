"""__main__ entry point: allows `python -m app --csv data/work_orders.csv`."""

from app.run import main
import sys

sys.exit(main())
