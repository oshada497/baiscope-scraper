# Gunicorn configuration settings
import multiprocessing

# Force single worker to maintain shared in-memory state
workers = 1

# Use threads to handle concurrent requests (status checks) while scraper runs
threads = 4

# Initial timeout
timeout = 120

# Log to stdout
accesslog = '-'
errorlog = '-'
