"""Rubin Schedule Viewer database creation entry point.

Populates a local database with relevant data from RSV to avoid
repeatedly querying the online Rubin database, which can be slow.

Entry point: `python -m rubin_sunrise.rsv.rsv_main` (DOESN'T WORK YET)

**Author:** Anna Ordog
"""

from datetime import datetime, timedelta
from astropy.time import Time
import subprocess
from rubin_sunrise.collector.lsst import rsv_service
from rubin_sunrise.dashboard.database_read import get_database
import numpy as np

def run_rsv():

    start_date = datetime(2026, 5, 1)

    db_name = "local_rsv"
    subprocess.run(["dropdb", db_name])
    subprocess.run(["createdb", db_name])
    subprocess.run(["psql", "-d", db_name, "-f", "schema_rsv.sql"])

    current_date = datetime.now()

    print(start_date)
    print(current_date)

    if Time(current_date) > Time(start_date):
        print('Checking database history...')


        conn, cur, flags_present = get_database(db_name=db_name)

        for j in range(0,70):

            print('==================')
            print(j)
            print('==================')

            cur.execute("""
                            SELECT time FROM visits
                            """)
            dates = cur.fetchall()#[-1][0].strftime("%Y-%m-%d")

            if dates == []:
                new_date = start_date
                print(f'No dates yet, start with {start_date.strftime("%Y-%m-%d")}')

            else:
                print(f'Last date in database is {dates[-1][0].strftime("%Y-%m-%d")}')
                new_date = dates[-1][0] + timedelta(days=1)
                print(f'Now processing {new_date}')

            visits = rsv_service(new_date)
            #print(visits.columns)
            status   = visits['execution_status']
            idx_good = np.where(status == 'Performed')[0]
            status   = list(status[idx_good])

            date_rsv = Time(visits['t_planning'], format='mjd').strftime("%Y-%m-%d")[idx_good]
            ra_rsv   = np.array(visits['s_ra'])[idx_good]
            dec_rsv  = np.array(visits['s_dec'])[idx_good]
            band_rsv = np.array(visits['band'])[idx_good]
            rot_rsv  = np.array(visits['rubin_rot_sky_pos'])[idx_good]

            for i in range(0,len(date_rsv)):
                cur.execute("""
                    INSERT INTO visits
                            (time, s_ra, s_dec, rubin_rot_sky_pos, band, execution_status)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (date_rsv[i],float(ra_rsv[i]),float(dec_rsv[i]),float(rot_rsv[i]),band_rsv[i], status[i]))
            conn.commit()

            cur.execute("SELECT pg_database_size(%s)", (db_name,))
            total_size = cur.fetchone()[0]
            print(total_size/1e6)
        


if __name__ == "__main__":
    run_rsv()