"""
displays.py: Generate HTML tables and figures for webpage display.

This module manages data preparation and HTML/Plotly figure generation for
the dashboard. It provides classes for different visualization types that 
wrap internal helper functions and coordinate with the database.

Public API
----------
- ``TableData`` - Cumulative visits summary table data.
- ``TargetMap`` - 2D visit coverage maps by filter band.
- ``TargetTimeSeries`` - Time series visits progress tracking.
- ``ObservabilityData`` - Future observability predictions.

**Author:** Anna Ordog, for CanDIAPL
"""
import pandas as pd
import numpy as np
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import plotly.io as pio
import matplotlib.colors as mcolors
import seaborn as sns
from astropy.time import Time
from datetime import timedelta

from rubin_dash.config import VERBOSE, DAYS_FORECAST
from rubin_dash.observability import el_vs_time

BANDS = ('u', 'g', 'r', 'i', 'z', 'y')
MASK_COLS = [f'{b}mask' for b in BANDS]
VISIT_COLS = [f'{b}visits' for b in BANDS]

def _populate_table(cur):
    """Query and format summary table data from user-specific database.

    Fetches the latest cumulative visits for all targets organized by
    group and member indices. Retrieves per-band visit counts and formats
    data for HTML table generation.

    Parameters
    ----------
    cur : psycopg2.cursor
        Database cursor with DictCursor factory.

    Returns
    -------
    dict
        Table data with keys: row_id, gr_name, ra, dec, gr_num, mem_num,
        and per-band visit counts (u, g, r, i, z, y).
    """
    cur.execute(f"""
        SELECT g.name_gr, g.group_id,
               m.member_id, m.ra_mem, m.dec_mem,
               {', '.join(f't.{c}' for c in VISIT_COLS)}
        FROM members m
        JOIN groups g ON g.group_id = m.group_id
        LEFT JOIN (
            SELECT DISTINCT ON (member_id)
                   member_id, {', '.join(VISIT_COLS)}
            FROM member_totals
            ORDER BY member_id, time DESC
        ) t ON t.member_id = m.member_id
        ORDER BY g.group_id, m.member_id
    """)
    rows = cur.fetchall()
    data = {}

    for col in ['row_id','gr_name','ra','dec','gr_num','mem_num']:
        data[col] = []
    for b in BANDS:
        data[b] = []

    prev_gid, mem_idx = None, 0
    for n, r in enumerate(rows):
        if r['group_id'] != prev_gid:
            prev_gid = r['group_id']
            mem_idx = 0
        else:
            mem_idx += 1

        data['gr_name'].append(r['name_gr'])
        data['ra'].append(r['ra_mem'])
        data['dec'].append(r['dec_mem'])
        data['gr_num'].append(r['group_id'])
        data['mem_num'].append(mem_idx)
        data['row_id'].append(f"{n:02d}")

        for b in BANDS:
            data[b].append(int(r[f'{b}visits'] or 0))

    return data

def _make_html_table(data):
    """Format table data as HTML for web display.

    Converts tabular data into an HTML table element with sortable columns.
    Excludes grouping-related debug columns if VERBOSE is False.

    Parameters
    ----------
    data : dict
        Table data from _populate_table().

    Returns
    -------
    str
        HTML string containing a formatted table with headers and rows.
    """
    df = pd.DataFrame(data, index=data['row_id'])
    df.index.name = "ID"

    # Define debug columns that should only be shown if VERBOSE is True
    debug_cols = ['row_id', 'gr_name', 'gr_num', 'mem_num']
    if not VERBOSE:
        df = df.drop(columns=debug_cols, errors='ignore')

    html = '<table class="data-table sortable-table">\n<thead>\n<tr>'

    # Index header first, then column headers
    html += f"<th>{df.index.name}</th>"
    for col in df.columns:
        html += f"<th>{col}</th>"
    html += "</tr>\n</thead>\n<tbody>\n"

    # Data rows
    for idx, row in df.iterrows():
        html += (
            f'<tr data-id="{idx}"'
            f' data-gn="{data["gr_num"][list(data["row_id"]).index(idx)]}"'
            f' data-mn="{data["mem_num"][list(data["row_id"]).index(idx)]}">'
        )
        html += f"<td>{idx}</td>"          # ID cell
        for col in df.columns:
            if col in BANDS:
                html += f"<td>{int(row[col])}</td>"
            elif col in ('ra', 'dec'):
                html += f"<td>{row[col]:.5f}</td>"
            else:
                html += f"<td>{row[col]}</td>"
        html += "</tr>\n"

    html += "</tbody>\n</table>"
    return html

def _populate_2D_map(gid, cur):
    """Query and format 2D visits map data from user-specific database.

    Fetches group coordinates, mask grid and data (daily and total), and 
    member coordinates for a target group. Prepares data for 2D heatmap 
    visualization.

    Parameters
    ----------
    gid : int
        Group ID identifying the target group.
    cur : psycopg2.cursor
        Database cursor with DictCursor factory.

    Returns
    -------
    dict
        Map data with keys: ra_gr, dec_gr (group center), ra_grid/dec_grid, 
        ra_mem/dec_mem (member positions), masks (daily and total visits).
    """
    # Group-level data
    cur.execute("""
        SELECT ra_gr, dec_gr, ra_grid, dec_grid
        FROM groups WHERE group_id = %s
    """, (gid,))
    grp = cur.fetchone()

    data = {}

    data['ra_gr']    = grp['ra_gr']
    data['dec_gr']   = grp['dec_gr']
    data['ra_grid']  = np.frombuffer(grp['ra_grid'])
    data['dec_grid'] = np.frombuffer(grp['dec_grid'])

    # Member coordinates
    cur.execute("""
        SELECT ra_mem, dec_mem FROM members
        WHERE group_id = %s ORDER BY member_id
    """, (gid,))
    members = cur.fetchall()
    data['ra_mem']  = np.array([m['ra_mem']  for m in members])
    data['dec_mem'] = np.array([m['dec_mem'] for m in members])

    # Masks
    cols = ', '.join(MASK_COLS)
    cur.execute(f"""
        SELECT mask_type, {cols}
        FROM group_masks
        WHERE group_id = %s AND mask_type IN ('latest', 'total')
    """, (gid,))

    data['masks'] = {}
    for row in cur.fetchall():
        mtype = row['mask_type']
        data['masks'][mtype] = {col: np.frombuffer(row[col], dtype=np.int16) for col in MASK_COLS}

    n = len(data['ra_grid'])
    for mtype in ('latest', 'total'):
        if mtype not in data['masks']:
            data[mtype] = {col: np.zeros(n) for col in MASK_COLS}

    return data

def _make_html_visits_map(data, idx_mem, maptype):
    """Generate 2D visits map as HTML for web display.

    Creates a Plotly figure with 6 subplots (one per filter band) showing 
    visit count heatmaps for the area covering one group of targets. 
    Overlays target group members and highlights the currently selected 
    member, defaulting to the first member (mn=0) of the first group (gn=1) 
    each time the webpage updates. Displays daily or cumulative coverage 
    depending on user selection.

    Parameters
    ----------
    data : dict
        Map data from _populate_2D_map().
    idx_mem : int
        Member index within the group (0-based, used for highlighting).
    maptype : str
        Either 'daily' (today's visits) or 'total' (cumulative).

    Returns
    -------
    str
        HTML string with embedded Plotly figure (div and script tags).
    """
    filter_names = [BANDS[0:3], BANDS[3:6]]
    mask_names = [MASK_COLS[0:3],MASK_COLS[3:6]]
    specs = [[{"type": "scatter"}]*3]*2

    fig = make_subplots(rows=2, cols=3,
                        subplot_titles = BANDS,
                        specs = specs,
                        vertical_spacing=0.1,
                        horizontal_spacing=0.01)
    title = f"<b>RA = {data['ra_mem'][idx_mem]:.5f}&deg;, dec = {data['dec_mem'][idx_mem]:.5f}&deg;</b>"
    fig.update_layout(title=dict(text=title, x=0.5, xanchor="center", font=dict(color='white')))

    if maptype == 'daily':
        Nmax = max(arr.max() for arr in data['masks']['latest'].values())+1
        Nmin = min(arr.min() for arr in data['masks']['latest'].values())
    else: 
        Nmax = max(arr.max() for arr in data['masks']['total'].values())+1
        Nmin = min(arr.min() for arr in data['masks']['total'].values())
    
    # Create integer tick values for colorbar
    space = int(np.ceil((Nmax - Nmin)/10))
    tickvals = list(np.arange(Nmin, Nmax+space, space))
    ticktext = [str(i) for i in tickvals]

    for row in range(1, 3):  # rows 1 and 2
        for col in range(1, 4):  # cols 1, 2, and 3

            if maptype == 'daily':
                z = data['masks']['latest'][mask_names[row-1][col-1]]
            else: 
                z = data['masks']['total'][mask_names[row-1][col-1]]

            fig.add_trace(go.Heatmap(z=z, x=data['ra_grid'], y=data['dec_grid'], 
                                     zmin=Nmin, zmax=Nmax,
                                     colorscale='Plasma',
                                     name=filter_names[row-1][col-1], 
                                     hovertemplate='RA: %{x}&deg;<br>Dec: %{y}&deg;<br>visits: %{z}<extra></extra>',
                                     colorbar=dict(outlinewidth=1, 
                                                   outlinecolor='black',
                                                   tickvals=tickvals,
                                                   ticktext=ticktext,
                                                   title=dict(text='Number of visits',
                                                                side='right',
                                                                font=dict(size=12)))
                                    ),row=row, col=col)
            
            fig.add_trace(go.Scatter(x=data['ra_mem'], y=data['dec_mem'],
                                    showlegend=False, mode='markers',
                                    marker=dict(size=3,
                                                color='black',
                                                symbol='circle')
                                    ),row=row, col=col)
            fig.add_trace(go.Scatter(x=[data['ra_mem'][idx_mem]],y=[data['dec_mem'][idx_mem]],
                                    mode='markers',showlegend=False,
                                    marker=dict(size=5,
                                                color='lightgreen',
                                                symbol='circle')
                                    ),row=row, col=col)    
                
            fig.update_xaxes(range=[data['ra_gr']+2.5, data['ra_gr']-2.5], constrain='domain', 
                            row=row, col=col)
            fig.update_yaxes(range=[data['dec_gr']-2.5, data['dec_gr']+2.5], constrain='domain', 
                            scaleanchor=f"x{col + (row-1)*3}", 
                            scaleratio=1, row=row, col=col)
            fig.for_each_annotation(lambda a: a.update(font_size=16, y=a.y+0.001))

    fig.update_xaxes(showline=True, linewidth=1, linecolor='white', mirror=True,
                    showgrid=False, zeroline=False, title_font=dict(color='white'), tickfont=dict(color='white'))
    fig.update_yaxes(showline=True, linewidth=1, linecolor='white', mirror=True,
                    showgrid=False, zeroline=False, title_font=dict(color='white'), tickfont=dict(color='white'))
    fig.update_xaxes(title_text="RA (deg.)", row=2)
    fig.update_yaxes(title_text="Dec (deg.)", col=1)
    fig.update_layout(showlegend=True, 
                      margin=dict(l=60, r=40, t=50, b=50),
                      plot_bgcolor='rgba(0,0,0,0)',
                      paper_bgcolor='rgba(0,0,0,0)',
                      font=dict(color='white'))

    fig.update_layout(autosize=True, width=None, height=None)

    fig_html = fig.to_html(full_html=False, div_id='figure1',
                        config={'responsive': True},
                        include_plotlyjs=False)   # ← rely on the CDN load
    
    return fig_html

def _populate_times_series(gid, idx_mem, cur):
    """Query and format time series visit data from user-specific database.

    Fetches daily and cumulative visit counts for a specific target (along 
    with coordinates) over time for each filter band.

    Parameters
    ----------
    gid : int
        Group ID identifying the target group.
    idx_mem : int
        Member index within the group (0-based).
    cur : psycopg2.cursor
        Database cursor with DictCursor factory.

    Returns
    -------
    dict
        Time series data with keys: 'daily' and 'total' (DataFrames with
        time and per-band visit counts), ra_mem/dec_mem (target position).
    """
    # Daily time series data
    cols = ', '.join([f'v.{c}' for c in VISIT_COLS])
    cur.execute(f"""
        SELECT v.time, {cols}
          FROM member_daily_visits v
          JOIN members m ON v.member_id = m.member_id
         WHERE m.group_id = %s
           AND m.member_idx = %s
         ORDER BY v.time
    """, (gid, idx_mem))

    data = {}

    data['daily'] = pd.DataFrame(cur.fetchall(), columns=['time'] + VISIT_COLS)

    # Cumulative time series data
    cols = ', '.join([f'v.{c}' for c in VISIT_COLS])
    cur.execute(f"""
        SELECT v.time, {cols}
          FROM member_totals v
          JOIN members m ON v.member_id = m.member_id
         WHERE m.group_id = %s
           AND m.member_idx = %s
         ORDER BY v.time
    """, (gid, idx_mem))

    data['total'] = pd.DataFrame(cur.fetchall(), columns=['time'] + VISIT_COLS)

    # Member coordinates
    cur.execute("""
        SELECT ra_mem, dec_mem FROM members
        WHERE group_id = %s ORDER BY member_id
    """, (gid,))
    members = cur.fetchall()
    data['ra_mem']  = np.array([m['ra_mem']  for m in members])
    data['dec_mem'] = np.array([m['dec_mem'] for m in members])

    return data

def _make_html_visits_plot(data, idx_mem, maptype):
    """Generate time series plot of visits over time as HTML for web display.

    Creates a Plotly plot showing visit count vs. time for each filter band.
    Includes markers and line styles to distinguish bands.

    Parameters
    ----------
    data : dict
        Time series data from _populate_times_series().
    idx_mem : int
        Member index within the group (0-based, used for title).
    maptype : str
        Either 'daily' (daily new visits) or 'total' (cumulative).

    Returns
    -------
    str
        HTML string with embedded Plotly figure (div and script tags).
    """
    fig = make_subplots(rows=1, cols=1,specs=[[{"type": "scatter"}]])
    title = f"<b>RA = {data['ra_mem'][idx_mem]:.5f}&deg;, dec = {data['dec_mem'][idx_mem]:.5f}&deg;</b>"
    fig.update_layout(title=dict(text=title, x=0.5, xanchor="center"))

    # Get colors from seaborn's colorblind palette with specific indices for better distinction
    cb_palette = sns.color_palette("colorblind", 10)
    color_indices = [0, 1, 2, 3, 4, 7]
    colors = [mcolors.rgb2hex(cb_palette[i]) for i in color_indices]
    symbols = ['circle', 'square', 'diamond', 'cross', 'x', 'star']

    # Loop through and add traces
    for color, name, visit, symbol in zip(colors, BANDS, VISIT_COLS, symbols):

        fig.add_trace(
            go.Scatter(x = pd.to_datetime(data[maptype]['time']),
                       y = data[maptype][visit],
                mode='lines+markers',
                name=name,
                line=dict(width=2, color=color),
                marker=dict(
                    size=7,
                    color=color,
                    symbol=symbol
                )
            ),
            row=1, col=1
        )

    fig.update_xaxes(title_text="Date", row=1, showgrid=True, gridcolor='#d3d3d3', showline=True, mirror=True, linecolor='white', title_font=dict(color='white'), tickfont=dict(color='white'))
    fig.update_yaxes(title_text="Number of visits", col=1, showgrid=True, gridcolor='#d3d3d3', showline=True, mirror=True, linecolor='white', title_font=dict(color='white'), tickfont=dict(color='white'))
    
    fig.update_layout(showlegend=True, margin=dict(l=60, r=40, t=50, b=50), plot_bgcolor='white', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='white'))

    fig.update_layout(autosize=True, width=None, height=None)

    fig_html = fig.to_html(full_html=False, div_id='figure2',
                        config={'responsive': True},
                        include_plotlyjs=False)   # ← rely on the CDN load

    return fig_html

def _populate_observability(gid, idx_mem, cur, date, flags_present):
    """Query and format observability forecast data from database.

    Fetches observability hours for a specific target over the forecast
    window (DAYS_FORECAST days from reference date). Also extracts target
    coordinates for sky position visualization.

    Parameters
    ----------
    gid : int
        Group ID identifying the target group.
    idx_mem : int
        Member index within the group (0-based).
    cur : psycopg2.cursor
        Database cursor with DictCursor factory.
    date : str or datetime
        Reference date (typically today) for start of forecast window.

    Returns
    -------
    dict
        Observability data with keys: ra, dec (target position),
        days_utc (astropy Time array), hours (observable hours per day).
    """
    data = {}

    # Extract the RA and dec from group and member indices:
    cur.execute(f"""
        SELECT ra_mem, dec_mem, member_id FROM members 
        WHERE group_id = %s AND member_idx =%s
        """, (gid,idx_mem))
    coords = cur.fetchone()
    data['ra']  = coords[0]
    data['dec'] = coords[1]
    mem_id = coords[2]

    # Extract the observability hours for the 60 days
    cur.execute("""
        SELECT time, hrs_obs FROM member_observability
        WHERE member_id = %s AND time BETWEEN %s AND %s
        ORDER BY time
    """, (mem_id, date, str(Time(date)+timedelta(days=DAYS_FORECAST))))
    rows = cur.fetchall()

    data['hours']   = []
    data['days_utc'] = []

    for row in rows:
        data['days_utc'].append(str(row['time']))  # Convert date to string
        data['hours'].append(row['hrs_obs'])

    # Convert list of date strings to astropy Time object for use in plotting
    if data['days_utc']:
        data['days_utc'] = Time(data['days_utc'])

    if flags_present:
        # Extract the user-defined observability hours for the 60 days
        cur.execute("""
            SELECT time, obs_flag FROM member_obs_flags
            WHERE member_id = %s AND time BETWEEN %s AND %s
            ORDER BY time
        """, (mem_id, date, str(Time(date)+timedelta(days=DAYS_FORECAST))))
        rows = cur.fetchall()

        flags = []

        for row in rows:
            #flip flag sign to allow filtering by multiplication
            flags.append(1 - row['obs_flag']) 
        print(len(data['hours']))
        print(len(flags))
        data['hours'] = data['hours'] * np.array(flags)

    return data

def _make_html_obs_plot(data, selected_date=None, window_days=5):
    """Generate observability forecast visualization as HTML for web display.

    Creates a 2-panel Plotly figure showing: observable hours per day 
    over next 30 days, and target elevation vs. time with day/night and 
    unobservable (el < 15 deg) regions shaded.

    Parameters
    ----------
    data : dict
        Observability data from _populate_observability().
    selected_date : str, optional
        ISO format date string (e.g., '2025-04-27'). The bottom panel will be 
        zoomed to show range of: this date + window_days.
    window_days : int, optional
        Number of days to show before and after selected_date (default: 5).

    Returns
    -------
    str
        HTML string with embedded Plotly figure (div and script tags).
    """
    fig = make_subplots(rows=2, cols=1, specs=[[{"type": "scatter"}]]*2)
    title = f"<b>RA = {data['ra']:.5f}&deg;, dec = {data['dec']:.5f}&deg;</b>"
    fig.update_layout(title=dict(text=title, x=0.5, xanchor="center"))

    # Calculate x-axis range for bottom panel and red dot position
    #utc_dates = data['utc'].iso
    #times = [Time(d) for d in utc_dates]
    #t_min = times[0]
    #t_max = times[-1]
    
    red_dot_date = data['days_utc'].iso[0]  # Default: first day
    
    if selected_date:
        t_utc, el, sunrise_list, sunset_list = el_vs_time(data['ra'], data['dec'], selected_date)
        #try:
        sel_t = Time(selected_date)
        times = [Time(d) for d in t_utc]
        diffs = [abs((t - sel_t).jd) for t in times]
        closest_idx = diffs.index(min(diffs))
        closest_time = times[closest_idx]
        red_dot_date = closest_time.iso.split('T')[0]  # Date portion only
        #except Exception:
        #    closest_time = t_min
        #    red_dot_date = t_min.iso.split('T')[0]
    else:
        t_utc, el, sunrise_list, sunset_list = el_vs_time(data['ra'], data['dec'], data['days_utc'][0])
    #    # Default: use first date
        closest_time = t_utc[0]#t_min
        red_dot_date = t_utc[0].iso.split('T')[0]
    
    # Calculate window: selected_date to selected_date + window_days
    window_start = closest_time
    window_end = closest_time + window_days
    #window_start = max(window_start, t_min)
    #window_end = min(window_end, t_max)
    
    bottom_x_min = window_start.iso
    bottom_x_max = window_end.iso

    fig.add_trace(
        go.Scatter(
            x=t_utc.iso, #data['utc'].iso,
            y=el, #data['el'],
            mode='lines',
            name = 'elevation',
            line=dict(width=1.5, color='yellow')
        ),
        row=2, col=1
    )
    fig.add_hrect(
        y0=-45, y1=0,           # horizontal lines to shade between
        fillcolor="darkolivegreen", 
        opacity=0.7,
        layer="above",
        line_width=0,
        row=2, col=1
    )
    fig.add_hrect(
        y0=0, y1=15,           # horizontal lines to shade between
        fillcolor="gray", 
        opacity=0.7,
        layer="above",
        line_width=0,
        row=2, col=1
    )
    fig.add_hrect(
        y0=86.5, y1=90,           # horizontal lines to shade between
        fillcolor="gray", 
        opacity=0.7,
        layer="above",
        line_width=0,
        row=2, col=1
    )
    for i in range(0,len(sunrise_list)):
        fig.add_shape(
            type="rect",
            x0=Time(sunrise_list[i]).iso, 
            x1=Time(sunset_list[i]).iso,
            y0=15,
            y1=86.5,
            fillcolor="deepskyblue",
            opacity=0.6,
            line_width=0,
            layer="above",
            xref="x2",
            yref="y2"
        )
    for i in range(0,len(sunrise_list)-1):
        fig.add_shape(
            type="rect",
            x0=Time(sunset_list[i]).iso, 
            x1=Time(sunrise_list[i+1]).iso,
            y0=15,
            y1=86.5,
            fillcolor="black",
            line_width=0,
            layer="below",
            xref="x2",
            yref="y2"
        )
    fig.add_trace(
        go.Scatter(
            x=data['days_utc'].iso,
            y=data['hours'],
            mode='lines',
            name = 'elevation',
            line=dict(width=2, color='black')
        ),
        row=1, col=1
    )
    
    # Add interactive point at the selected date
    # Find the y-value (hours) corresponding to the red_dot_date
    red_dot_idx = None
    for i, d in enumerate(data['days_utc'].iso):
        if d.startswith(red_dot_date):
            red_dot_idx = i
            break
    
    if red_dot_idx is None:
        red_dot_idx = 0  # Fallback to first
    
    fig.add_trace(
        go.Scatter(
            x=[data['days_utc'].iso[red_dot_idx]],
            y=[data['hours'][red_dot_idx]],
            mode='markers',
            name='selected day',
            marker=dict(size=8, color='red', symbol='circle'),
            showlegend=False
        ),
        row=1, col=1
    )
    
    # Add shaded region to top panel showing the zoomed window
    fig.add_vrect(
        x0=window_start.iso, 
        x1=window_end.iso,
        fillcolor="salmon",
        opacity=0.2,
        layer="below",
        line_width=0,
        row=1, col=1
    )

    # Set top panel x-axis range (full 30 days)
    fig.update_xaxes(title_text="Date", 
                     range=[data['days_utc'].iso[0], data['days_utc'].iso[-1]], 
                     showgrid=False, tickformat="%d/%m/%y",
                     showline=True, mirror=True,
                     row=1, col=1)
    
    # Set bottom panel x-axis range (zoomed to window around selected_date)
    fig.update_xaxes(title_text="Date", 
                     range=[bottom_x_min, bottom_x_max],
                     showgrid=False, tickformat="%d/%m/%y",
                     showline=True, mirror=True,
                     row=2, col=1)
    fig.update_yaxes(
        title_text="Hours observable",
        range=[0, 15],
        row=1, col=1,
        showgrid=True,
        gridcolor='#d3d3d3',
        tickvals=[0, 3, 6, 9, 12, 15],
        ticktext=['0', '3', '6', '9', '12', '15'],
        showline=True, mirror=True
    )
    fig.update_yaxes(
        title_text="Elevation",
        range=[-45, 90],
        showgrid=False,
        zeroline=False,
        tickvals=[-45, 0, 45, 90],
        ticktext=['-45°', '0°', '45°', '90°'],
        showline=True, mirror=True,
        row=2, col=1,
        linecolor='white', title_font=dict(color='white'), tickfont=dict(color='white')
    )
    
    fig.update_xaxes(linecolor='white', row=1, col=1, title_font=dict(color='white'), tickfont=dict(color='white'))
    fig.update_xaxes(linecolor='white', row=2, col=1, title_font=dict(color='white'), tickfont=dict(color='white'))
    fig.update_yaxes(linecolor='white', row=1, col=1, title_font=dict(color='white'), tickfont=dict(color='white'))
    
    fig.update_layout(showlegend=False, margin=dict(l=60, r=40, t=50, b=50), plot_bgcolor='white', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='white')) 
    fig.update_layout(autosize=True, width=None, height=None)

    fig_html = fig.to_html(full_html=False, div_id='figure3',
                        config={'responsive': True},
                        include_plotlyjs=False)   # ← rely on the CDN load

    return fig_html



class BasePlot:
    """Base class for plot objects.
    
    Provides common initialization and description tracking for plot-related
    classes. NOT YET USED!
    
    Parameters
    ----------
    description : str, optional
        Description of the plot object. Default is "Base Plot".
    
    Attributes
    ----------
    description : str
        Description of the plot object.
    """

    def __init__(self, description: str = "Base Plot"):
        self.description = description

class TableData:
    """Container for cumulative visits summary table data.
    
    Stores table data including visit counts per filter band and target
    coordinates. Data is fetched from the database and formatted by the
    `make_html_table()` method for web display.
    
    Parameters
    ----------
    cur : psycopg2.cursor
        Database cursor with DictCursor factory for safe column access.
    
    Attributes
    ----------
    data : dict
        Dictionary containing table data with visits counts per filter band
        and target coordinate information.
    """

    def __init__(self, cur, description: str = "Table data object"):
        self.description = description
        self.data = _populate_table(cur)

    def make_html_table(self):
        """Format table data as HTML for web display.

        Converts tabular data into an HTML table element with sortable columns.
        Excludes grouping-related debug columns if VERBOSE is False.

        Returns
        -------
        str
            HTML string containing a formatted table with headers and rows.
        """
        return _make_html_table(self.data)
    

class TargetMap:
    """Container for 2D visit coverage map data by filter band.
    
    Stores grid coordinates, mask data (daily and cumulative), and target
    group coordinates. Data is fetched from the database and visualized by
    the `make_html_visits_map()` method for web display.
    
    Parameters
    ----------
    gid : int
        Group ID identifying the target group.
    cur : psycopg2.cursor
        Database cursor with DictCursor factory for safe column access.
    
    Attributes
    ----------
    data : dict
        Dictionary containing map data including target group coordinates, 
        grid coordinates, group member coordinates, and mask counts by band.
    """

    def __init__(self, gid, cur, description: str = "2D map object"):
        self.description = description
        self.data = _populate_2D_map(gid, cur)

    def make_html_visits_map(self, idx_mem, maptype):
        """Generate 2D visits map as HTML for web display.

        Creates a Plotly figure with 6 subplots (one per filter band) showing 
        visit count heatmaps for the area covering one group of targets. 
        Overlays target group members and highlights the currently selected 
        member, defaulting to the first member (mn=0) of the first group (gn=1) 
        each time the webpage updates. Displays daily or cumulative coverage 
        depending on user selection.

        Parameters
        ----------
        idx_mem : int
            Member index within the group (0-based, used for highlighting).
        maptype : str
            Either 'daily' (today's visits) or 'total' (cumulative).

        Returns
        -------
        str
            HTML string with embedded Plotly figure (div and script tags).
        """
        return _make_html_visits_map(self.data, idx_mem, maptype)


class TargetTimeSeries:
    """Container for time series visits progress data.
    
    Stores historical daily and cumulative visit data for a target over
    time, organized by filter band. Data is fetched from the database and
    visualized by the `make_html_visits_plot()` method for web display.
    
    Parameters
    ----------
    gid : int
        Group ID identifying the target group.
    idx_mem : int
        Member index within the group (0-based).
    cur : psycopg2.cursor
        Database cursor with DictCursor factory for safe column access.

    Attributes
    ----------
    data : dict
        Dictionary containing time series data with 'daily' and 'total'
        DataFrames indexed by date with visit counts per band.
    """

    def __init__(self, gid, idx_mem, cur, 
                 description: str = "Time series object"):
        self.description = description
        self.data = _populate_times_series(gid, idx_mem, cur)

    def make_html_visits_plot(self, idx_mem, maptype):
        """Generate time series plot of visits over time as HTML for web 
        display.

        Creates a Plotly plot showing visit count vs. time for each filter 
        band.

        Parameters
        ----------
        idx_mem : int
            Member index within the group (0-based, used for title).
        maptype : str
            Either 'daily' (daily new visits) or 'total' (cumulative).

        Returns
        -------
        str
            HTML string with embedded Plotly figure (div and script tags).
        """
        return _make_html_visits_plot(self.data, idx_mem, maptype)


class ObservabilityData:
    """Container for future observability predictions.
    
    Stores computed observability data including altitude/azimuth,
    sunrise/sunset times, and observable hours for a target based on Vera
    C. Rubin Observatory location. Data is computed from input coordinates
    and dates, and visualized by the `make_html_obs_plot()` method for web
    display.
    
    Parameters
    ----------
    gid : int
        Group ID identifying the target group.
    idx_mem : int
        Member index within the group (0-based).
    cur : psycopg2.cursor
        Database cursor with DictCursor factory for safe column access.
    date : str or datetime
        Reference date (typically today) for start of observability window.

    Attributes
    ----------
    data : dict
        Dictionary containing observability data including coordinates,
        time arrays, altitude/azimuth, sunrise/sunset times, and
        observable hours per day.
    """

    def __init__(self, gid, idx_mem, cur, date, flags_present,
                 description: str = "Observability data object"):
        self.description = description
        self.data = _populate_observability(gid, idx_mem, cur, date, flags_present)

    def make_html_obs_plot(self, selected_date=None, window_days=5):
        """Generate observability forecast visualization as HTML for 
        web display.

        Creates a 2-panel Plotly figure showing: observable hours per day
        over next 30 days, and target elevation vs. time with day/night and
        unobservable (el < 15 deg) regions shaded.

        Parameters
        ----------
        selected_date : str, optional
            ISO format date string (e.g., '2025-04-27'). The bottom panel
            will be zoomed to show range of: this date + window_days.
        window_days : int, optional
            Number of days to show after selected_date (default: 5).

        Returns
        -------
        str
            HTML string with embedded Plotly figure (div and script tags).
        """
        return _make_html_obs_plot(self.data, selected_date, window_days)