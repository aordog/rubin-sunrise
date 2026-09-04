import numpy as np
#import random
import csv
#import astropy.units as u
#from astropy.time import Time
#from astropy.coordinates import get_body, SkyCoord
import os
import time
import subprocess

Nmin = 20
Nmax = 500

for i in range(0,3):

    db_name = f'testdb_{i:03d}'
    file_name = f'testfile_{i:03d}.txt'

    N = int(np.ceil(np.random.uniform(Nmin,Nmax)))

    ra_list  = np.random.uniform( 0, 360, N)
    dec_list = np.random.uniform(-90, 20, N)

    rows = zip(ra_list, dec_list)

    with open(f'data/{file_name}', "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, delimiter=";")
        writer.writerow(["ra", "dec"]) 
        writer.writerows(rows)

    subprocess.Popen(f"python -m rubin_sunrise collector --db-name {db_name} --query-file {file_name}".split())

    time.sleep(90)

    print(db_name, N)