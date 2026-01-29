"""
Presale Trajectory Mode

Displays presale buildup curves, acceleration metrics, and competitive intelligence
for upcoming film releases across Top 12 circuits.

Features:
- Buildup curves showing ticket sales trajectory
- Circuit leaderboards and rankings
- Format mix analysis (IMAX%, Dolby%, Premium%)
- Acceleration alerts (day-over-day changes)
- Marcus competitive positioning
"""
import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import altair as alt
from app import config

def render_presale_trajectory_mode():
    """Main rendering function for Presale Trajectory mode"""
    st.title("🎟️ Presale Trajectory Analysis")
    st.info("Track presale buildup and acceleration across Top 12 circuits for upcoming releases.")
    
    # Load available films with presale data
    try:
        conn = sqlite3.connect(config.DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT film_title, release_date, 
                   MAX(snapshot_date) as latest_snapshot,
                   SUM(total_tickets_sold) as total_presales
            FROM circuit_presales 
            GROUP BY film_title, release_date
            ORDER BY total_presales DESC
        """)
        available_films = cursor.fetchall()
        conn.close()
        
        if not available_films:
            st.warning("⚠️ No presale data available. Run: `python sync_engine.py --presales`")
            st.code("python sync_engine.py --presales", language="bash")
            return
        
    except Exception as e:
        st.error(f"❌ Error loading presale data: {e}")
        return
    
    # Film selection
    film_options = {f"{row[0]} (Release: {row[1]}, {row[3]:,} tickets)": row[0] for row in available_films}
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        selected_film_display = st.selectbox("Select Film", options=list(film_options.keys()))
        selected_film = film_options[selected_film_display]
    
    with col2:
        refresh = st.button("🔄 Refresh Data", use_container_width=True, type="primary")
    
    st.divider()
    
    # Load film presale data
    df = load_presale_data(selected_film)
    
    if df.empty:
        st.warning(f"No presale data for {selected_film}")
        return
    
    # Display tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📈 Buildup Curves", 
        "🏆 Circuit Leaderboards",
        "⚡ Acceleration Alerts",
        "🎬 Format Analysis",
        "📊 Marcus vs Competition"
    ])
    
    with tab1:
        render_buildup_curves(df, selected_film)
    
    with tab2:
        render_circuit_leaderboards(df, selected_film)
    
    with tab3:
        render_acceleration_alerts(df, selected_film)
    
    with tab4:
        render_format_analysis(df, selected_film)
    
    with tab5:
        render_marcus_comparison(df, selected_film)


def load_presale_data(film_title: str) -> pd.DataFrame:
    """Load presale trajectory data for a specific film"""
    try:
        conn = sqlite3.connect(config.DB_FILE)
        
        query = """
            SELECT 
                circuit_name,
                film_title,
                release_date,
                snapshot_date,
                days_before_release,
                total_tickets_sold,
                total_revenue,
                total_showtimes,
                total_theaters,
                avg_tickets_per_show,
                avg_tickets_per_theater,
                avg_ticket_price,
                tickets_imax,
                tickets_dolby,
                tickets_3d,
                tickets_premium,
                tickets_standard
            FROM circuit_presales
            WHERE film_title = ?
            ORDER BY circuit_name, snapshot_date
        """
        
        df = pd.read_sql_query(query, conn, params=(film_title,))
        conn.close()
        
        # Convert dates
        df['snapshot_date'] = pd.to_datetime(df['snapshot_date'])
        df['release_date'] = pd.to_datetime(df['release_date'])
        
        return df
        
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame()


def render_buildup_curves(df: pd.DataFrame, film_title: str):
    """Display presale buildup curves by circuit"""
    st.subheader("📈 Presale Buildup Curves")
    st.caption(f"Daily ticket sales trajectory for {film_title}")
    
    # Prepare data for chart
    chart_data = df[['circuit_name', 'snapshot_date', 'total_tickets_sold', 'days_before_release']].copy()
    
    # Highlight Marcus circuits
    chart_data['is_marcus'] = chart_data['circuit_name'].isin(['Legacy Theatres', 'Movie Tavern'])
    
    # Create line chart
    chart = alt.Chart(chart_data).mark_line(point=True).encode(
        x=alt.X('snapshot_date:T', title='Date', axis=alt.Axis(format='%b %d')),
        y=alt.Y('total_tickets_sold:Q', title='Total Tickets Sold'),
        color=alt.Color('circuit_name:N', 
                        title='Circuit',
                        scale=alt.Scale(domain=['Legacy Theatres', 'Movie Tavern'], 
                                       range=['#FFD700', '#FFA500'])),
        strokeWidth=alt.condition(
            alt.datum.is_marcus,
            alt.value(3),
            alt.value(1.5)
        ),
        tooltip=[
            alt.Tooltip('circuit_name:N', title='Circuit'),
            alt.Tooltip('snapshot_date:T', title='Date', format='%b %d, %Y'),
            alt.Tooltip('days_before_release:Q', title='Days Before Release'),
            alt.Tooltip('total_tickets_sold:Q', title='Tickets Sold', format=',')
        ]
    ).properties(
        height=400,
        title=f"Presale Trajectory: {film_title}"
    ).interactive()
    
    st.altair_chart(chart, use_container_width=True)
    
    # Summary stats
    latest = df[df['snapshot_date'] == df['snapshot_date'].max()]
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Presales", f"{latest['total_tickets_sold'].sum():,}")
    
    with col2:
        st.metric("Avg Price", f"${latest['avg_ticket_price'].mean():.2f}")
    
    with col3:
        st.metric("Total Theaters", f"{latest['total_theaters'].sum():,}")
    
    with col4:
        days_out = latest['days_before_release'].iloc[0] if not latest.empty else 0
        st.metric("Days to Release", days_out)


def render_circuit_leaderboards(df: pd.DataFrame, film_title: str):
    """Display circuit rankings and leaderboards"""
    st.subheader("🏆 Circuit Presale Leaderboards")
    
    # Get latest snapshot
    latest = df[df['snapshot_date'] == df['snapshot_date'].max()].copy()
    latest = latest.sort_values('total_tickets_sold', ascending=False)
    
    # Calculate market share
    total_presales = latest['total_tickets_sold'].sum()
    latest['market_share'] = (latest['total_tickets_sold'] / total_presales * 100).round(1)
    
    # Highlight Marcus
    def highlight_marcus(row):
        if row['circuit_name'] in ['Legacy Theatres', 'Movie Tavern']:
            return ['background-color: #FFD70030'] * len(row)
        return [''] * len(row)
    
    # Display leaderboard
    leaderboard = latest[[
        'circuit_name', 'total_tickets_sold', 'total_theaters', 
        'avg_tickets_per_theater', 'market_share', 'avg_ticket_price'
    ]].copy()
    
    leaderboard.columns = ['Circuit', 'Total Tickets', 'Theaters', 'Tickets/Theater', 'Market Share %', 'Avg Price']
    
    styled_df = leaderboard.style.apply(highlight_marcus, axis=1).format({
        'Total Tickets': '{:,.0f}',
        'Theaters': '{:,.0f}',
        'Tickets/Theater': '{:.1f}',
        'Market Share %': '{:.1f}%',
        'Avg Price': '${:.2f}'
    })
    
    st.dataframe(styled_df, use_container_width=True, hide_index=True)
    
    # Marcus positioning
    marcus_circuits = latest[latest['circuit_name'].isin(['Legacy Theatres', 'Movie Tavern'])]
    if not marcus_circuits.empty:
        st.markdown("### 🎯 Marcus Position")
        marcus_total = marcus_circuits['total_tickets_sold'].sum()
        marcus_share = (marcus_total / total_presales * 100)
        marcus_rank = (latest['total_tickets_sold'] > marcus_total).sum() + 1
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Marcus Total", f"{marcus_total:,} tickets")
        with col2:
            st.metric("Market Share", f"{marcus_share:.1f}%")
        with col3:
            st.metric("Ranking", f"#{marcus_rank} of {len(latest)}")


def render_acceleration_alerts(df: pd.DataFrame, film_title: str):
    """Display day-over-day acceleration metrics and alerts"""
    st.subheader("⚡ Presale Acceleration Alerts")
    st.caption("Day-over-day changes and momentum indicators")
    
    # Calculate day-over-day changes
    df_sorted = df.sort_values(['circuit_name', 'snapshot_date'])
    df_sorted['prev_tickets'] = df_sorted.groupby('circuit_name')['total_tickets_sold'].shift(1)
    df_sorted['daily_change'] = df_sorted['total_tickets_sold'] - df_sorted['prev_tickets']
    df_sorted['pct_change'] = ((df_sorted['daily_change'] / df_sorted['prev_tickets']) * 100).round(1)
    
    # Get latest changes
    latest = df_sorted[df_sorted['snapshot_date'] == df_sorted['snapshot_date'].max()].copy()
    latest = latest[latest['prev_tickets'].notna()]  # Only circuits with previous data
    
    if latest.empty:
        st.info("📊 Acceleration metrics will be available after second snapshot")
        return
    
    # Identify significant changes (>40%)
    alerts = latest[abs(latest['pct_change']) > 40].copy()
    
    if not alerts.empty:
        st.markdown("### 🚨 High Velocity Changes (>40%)")
        for _, row in alerts.iterrows():
            icon = "🟢" if row['pct_change'] > 0 else "🔴"
            st.warning(f"{icon} **{row['circuit_name']}**: {row['pct_change']:+.1f}% ({row['daily_change']:+,} tickets)")
    
    # Show all changes
    st.markdown("### 📊 All Circuits - Daily Momentum")
    
    change_data = latest[['circuit_name', 'daily_change', 'pct_change', 'total_tickets_sold']].copy()
    change_data = change_data.sort_values('pct_change', ascending=False)
    
    # Highlight Marcus
    def highlight_acceleration(row):
        if row['circuit_name'] in ['Legacy Theatres', 'Movie Tavern']:
            return ['background-color: #FFD70030'] * len(row)
        elif abs(row['pct_change']) > 40:
            return ['background-color: #FF000020'] * len(row)
        return [''] * len(row)
    
    change_data.columns = ['Circuit', 'Daily Change', '% Change', 'Current Total']
    
    styled_change = change_data.style.apply(highlight_acceleration, axis=1).format({
        'Daily Change': '{:+,.0f}',
        '% Change': '{:+.1f}%',
        'Current Total': '{:,.0f}'
    })
    
    st.dataframe(styled_change, use_container_width=True, hide_index=True)
    
    # Acceleration chart
    chart = alt.Chart(latest).mark_bar().encode(
        x=alt.X('pct_change:Q', title='% Change vs Yesterday'),
        y=alt.Y('circuit_name:N', title='Circuit', sort='-x'),
        color=alt.condition(
            alt.datum.pct_change > 0,
            alt.value('#2ecc71'),
            alt.value('#e74c3c')
        ),
        tooltip=[
            alt.Tooltip('circuit_name:N', title='Circuit'),
            alt.Tooltip('pct_change:Q', title='% Change', format='+.1f'),
            alt.Tooltip('daily_change:Q', title='Daily Change', format='+,')
        ]
    ).properties(height=300)
    
    st.altair_chart(chart, use_container_width=True)


def render_format_analysis(df: pd.DataFrame, film_title: str):
    """Display format mix analysis for presales"""
    st.subheader("🎬 Format Mix Analysis")
    st.caption("Presale ticket distribution by format across circuits")
    
    # Get latest snapshot
    latest = df[df['snapshot_date'] == df['snapshot_date'].max()].copy()
    
    # Calculate format percentages
    latest['imax_pct'] = (latest['tickets_imax'] / latest['total_tickets_sold'] * 100).round(1)
    latest['dolby_pct'] = (latest['tickets_dolby'] / latest['total_tickets_sold'] * 100).round(1)
    latest['3d_pct'] = (latest['tickets_3d'] / latest['total_tickets_sold'] * 100).round(1)
    latest['premium_pct'] = (latest['tickets_premium'] / latest['total_tickets_sold'] * 100).round(1)
    latest['standard_pct'] = (latest['tickets_standard'] / latest['total_tickets_sold'] * 100).round(1)
    latest['plf_total_pct'] = latest[['imax_pct', 'dolby_pct', 'premium_pct']].sum(axis=1).round(1)
    
    # Format breakdown table
    format_table = latest[[
        'circuit_name', 'total_tickets_sold', 'imax_pct', 'dolby_pct', 
        '3d_pct', 'premium_pct', 'standard_pct', 'plf_total_pct'
    ]].sort_values('plf_total_pct', ascending=False)
    
    format_table.columns = ['Circuit', 'Total Tickets', 'IMAX %', 'Dolby %', '3D %', 'Premium %', 'Standard %', 'Total PLF %']
    
    def highlight_marcus(row):
        if row['Circuit'] in ['Legacy Theatres', 'Movie Tavern']:
            return ['background-color: #FFD70030'] * len(row)
        return [''] * len(row)
    
    styled_format = format_table.style.apply(highlight_marcus, axis=1).format({
        'Total Tickets': '{:,.0f}',
        'IMAX %': '{:.1f}%',
        'Dolby %': '{:.1f}%',
        '3D %': '{:.1f}%',
        'Premium %': '{:.1f}%',
        'Standard %': '{:.1f}%',
        'Total PLF %': '{:.1f}%'
    })
    
    st.dataframe(styled_format, use_container_width=True, hide_index=True)
    
    # PLF rankings
    st.markdown("### 🏆 Premium Format Leaders")
    top_plf = format_table.nlargest(5, 'Total PLF %')[['Circuit', 'Total PLF %', 'IMAX %', 'Dolby %']]
    st.dataframe(top_plf, use_container_width=True, hide_index=True)


def render_marcus_comparison(df: pd.DataFrame, film_title: str):
    """Display Marcus competitive positioning analysis"""
    st.subheader("📊 Marcus vs Competition")
    st.caption("Marcus (Legacy + Movie Tavern) performance benchmarking")
    
    # Get latest snapshot
    latest = df[df['snapshot_date'] == df['snapshot_date'].max()].copy()
    
    # Separate Marcus and competitors
    marcus = latest[latest['circuit_name'].isin(['Legacy Theatres', 'Movie Tavern'])]
    competitors = latest[~latest['circuit_name'].isin(['Legacy Theatres', 'Movie Tavern'])]
    
    if marcus.empty:
        st.info("No Marcus data available")
        return
    
    # Aggregate Marcus totals
    marcus_total_tickets = marcus['total_tickets_sold'].sum()
    marcus_total_theaters = marcus['total_theaters'].sum()
    marcus_avg_price = marcus['avg_ticket_price'].mean()
    marcus_tickets_per_theater = marcus_total_tickets / marcus_total_theaters if marcus_total_theaters > 0 else 0
    
    # Competitor averages
    comp_avg_tickets = competitors['total_tickets_sold'].mean()
    comp_avg_theaters = competitors['total_theaters'].mean()
    comp_avg_price = competitors['avg_ticket_price'].mean()
    comp_avg_tickets_per_theater = competitors['avg_tickets_per_theater'].mean()
    
    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        delta_tickets = marcus_total_tickets - comp_avg_tickets
        st.metric("Total Tickets", f"{marcus_total_tickets:,}", 
                 delta=f"{delta_tickets:+,.0f} vs avg", 
                 delta_color="normal")
    
    with col2:
        delta_theaters = marcus_total_theaters - comp_avg_theaters
        st.metric("Total Theaters", f"{marcus_total_theaters:,}", 
                 delta=f"{delta_theaters:+,.0f} vs avg",
                 delta_color="normal")
    
    with col3:
        delta_price = marcus_avg_price - comp_avg_price
        st.metric("Avg Ticket Price", f"${marcus_avg_price:.2f}", 
                 delta=f"${delta_price:+.2f} vs avg",
                 delta_color="normal")
    
    with col4:
        delta_per_theater = marcus_tickets_per_theater - comp_avg_tickets_per_theater
        st.metric("Tickets/Theater", f"{marcus_tickets_per_theater:.1f}", 
                 delta=f"{delta_per_theater:+.1f} vs avg",
                 delta_color="normal")
    
    # Comparison table
    st.markdown("### 📋 Detailed Comparison")
    
    comparison = pd.DataFrame({
        'Metric': ['Total Tickets', 'Avg Tickets/Theater', 'Avg Price', 'Total PLF %'],
        'Marcus': [
            marcus_total_tickets,
            marcus_tickets_per_theater,
            marcus_avg_price,
            ((marcus['tickets_imax'].sum() + marcus['tickets_dolby'].sum() + marcus['tickets_premium'].sum()) / marcus_total_tickets * 100) if marcus_total_tickets > 0 else 0
        ],
        'Competitor Avg': [
            comp_avg_tickets,
            comp_avg_tickets_per_theater,
            comp_avg_price,
            competitors[['tickets_imax', 'tickets_dolby', 'tickets_premium']].sum(axis=1).sum() / competitors['total_tickets_sold'].sum() * 100 if not competitors.empty else 0
        ]
    })
    
    comparison['Difference'] = comparison['Marcus'] - comparison['Competitor Avg']
    comparison['% Diff'] = (comparison['Difference'] / comparison['Competitor Avg'] * 100).round(1)
    
    st.dataframe(comparison.style.format({
        'Marcus': '{:,.1f}',
        'Competitor Avg': '{:,.1f}',
        'Difference': '{:+,.1f}',
        '% Diff': '{:+.1f}%'
    }), use_container_width=True, hide_index=True)
