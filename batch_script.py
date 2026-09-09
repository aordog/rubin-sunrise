import numpy as np
#import random
import csv
#import astropy.units as u
#from astropy.time import Time
#from astropy.coordinates import get_body, SkyCoord
import sys
import time
import subprocess
import signal

Nmin = 15
Nmax = 500

processes = []


def cleanup(signum=None, frame=None):
    """Terminate all child processes."""
    print("\nTerminating child processes...")
    for proc in processes:
        if proc.poll() is None:
            proc.terminate()
    for proc in processes:
        proc.wait(timeout=10)
    print("Done.")


signal.signal(signal.SIGINT, cleanup)

try:
    for i in range(0, 20):
        db_name = f'testdb_{i:03d}'
        file_name = f'testfile_{i:03d}.txt'

        N = int(np.ceil(np.random.uniform(Nmin, Nmax)))

        ra_list = np.random.uniform(0, 360, N)
        dec_list = np.random.uniform(-90, 20, N)

        rows = zip(ra_list, dec_list)

        with open(f'data/{file_name}', "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow(["ra", "dec"])
            writer.writerows(rows)

        proc = subprocess.Popen(
            f"python -m rubin_sunrise collector --db-name {db_name} --query-file {file_name}".split()
        )
        processes.append(proc)
        print(f"Started {db_name} (pid: {proc.pid})")

        time.sleep(10)
        print(f"{db_name}: N={N}")

    print("\nWaiting for all processes to finish...")
    for proc in processes:
        proc.wait()

except KeyboardInterrupt:
    cleanup()

    sys.exit(0)