"""
Circuit Benchmarks Mode

Displays nationwide circuit performance metrics for competitive intelligence.
Supports the Top 10 Circuits Report with operational insights.
"""
import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import io
from app import config

def render_circuit_benchmarks_mode():
    """Main rendering function for Circuit Benchmarks mode"""
    st.title("🌎 Nationwide Circuit Benchmarks")
    st.info("Competitive intelligence for the Top 12 circuits nationwide. Data synced weekly from EntTelligence.")
    
    # Load available weeks
    try:
        conn = sqlite3.connect(config.DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT week_ending_date 
            FROM circuit_benchmarks 
            ORDER BY week_ending_date DESC
        """)
        available_weeks = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        if not available_weeks:
            st.warning("⚠️ No nationwide data synced yet. Go to Data Management mode and click '🌎 Run Nationwide Sync'")
            return
        
    except Exception as e:
        st.error(f"❌ Error loading circuit data: {e}")
        return
    
    # Period selection
    col1, col2 = st.columns([2, 1])
    
    with col1:
        selected_week = st.selectbox(
            "Select Report Period",
            options=available_weeks,
            format_func=lambda x: f"{x} ({(datetime.strptime(x, '%Y-%m-%d') - timedelta(days=6)).strftime('%m/%d')} - {datetime.strptime(x, '%Y-%m-%d').strftime('%m/%d/%Y')})"
        )
    
    with col2:
        # Export button
        if st.button("📊 Export to Excel", use_container_width=True, type="primary"):
            excel_data = generate_excel_report(selected_week)
            st.download_button(
                label="💾 Download Excel Workbook",
                data=excel_data,
                file_name=f"Circuit_Benchmarks_{selected_week}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
    
    st.divider()
    
    # Load data for selected week
    df = load_circuit_data(selected_week)
    
    if df.empty:
        st.warning(f"No data for week ending {selected_week}")
        return
    
    # Display tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Overview", 
        "🎬 Format Mix", 
        "⏰ Daypart Strategy", 
        "💰 Pricing"
    ])
    
    with tab1:
        render_overview_tab(df)
    
    with tab2:
        render_format_tab(df)
    
    with tab3:
        render_daypart_tab(df)
    
    with tab4:
        render_pricing_tab(df)


def load_circuit_data(week_ending_date: str) -> pd.DataFrame:
    """Load circuit benchmark data for a specific week"""
    try:
        conn = sqlite3.connect(config.DB_FILE)
        
        query = """
            SELECT 
                circuit_name,
                total_showtimes,
                total_capacity,
                total_theaters,
                total_films,
                avg_screens_per_film,
                avg_showtimes_per_theater,
                format_standard_pct,
                format_imax_pct,
                format_dolby_pct,
                format_3d_pct,
                format_other_premium_pct,
                plf_total_pct,
                daypart_matinee_pct,
                daypart_evening_pct,
                daypart_late_pct,
                avg_price_general,
                avg_price_child,
                avg_price_senior
            FROM circuit_benchmarks
            WHERE week_ending_date = ?
            ORDER BY total_showtimes DESC
        """
        
        df = pd.read_sql_query(query, conn, params=[week_ending_date])
        conn.close()
        
        return df
        
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame()


def render_overview_tab(df: pd.DataFrame):
    """Render overview comparison table"""
    st.subheader("Circuit Performance Overview")
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    
    marcus_data = df[df['circuit_name'].str.contains('Marcus', case=False)]
    if not marcus_data.empty:
        marcus_row = marcus_data.iloc[0]
        
        with col1:
            st.metric("Marcus Showtimes", f"{marcus_row['total_showtimes']:,.0f}")
        with col2:
            st.metric("Marcus Theaters", f"{marcus_row['total_theaters']:.0f}")
        with col3:
            st.metric("Marcus PLF %", f"{marcus_row['plf_total_pct']:.1f}%")
        with col4:
            avg_plf = df['plf_total_pct'].mean()
            delta = marcus_row['plf_total_pct'] - avg_plf
            st.metric("vs Top 10 Avg PLF", f"{delta:+.1f}%", 
                     help=f"Marcus: {marcus_row['plf_total_pct']:.1f}% vs Industry: {avg_plf:.1f}%")
    
    st.divider()
    
    # Main comparison table
    display_df = df.copy()
    display_df.columns = [
        'Circuit', 'Showtimes', 'Capacity', 'Theaters', 'Films',
        'Screens/Film', 'Shows/Theater', 
        'Standard %', 'IMAX %', 'Dolby %', '3D %', 'Other PLF %', 
        'Total PLF %',
        'Matinee %', 'Evening %', 'Late %',
        'Avg $ General', 'Avg $ Child', 'Avg $ Senior'
    ]
    
    # Format columns
    format_dict = {
        'Showtimes': '{:,.0f}',
        'Capacity': '{:,.0f}',
        'Theaters': '{:.0f}',
        'Films': '{:.0f}',
        'Screens/Film': '{:.1f}',
        'Shows/Theater': '{:.1f}',
        'Standard %': '{:.1f}%',
        'IMAX %': '{:.1f}%',
        'Dolby %': '{:.1f}%',
        '3D %': '{:.1f}%',
        'Other PLF %': '{:.1f}%',
        'Total PLF %': '{:.1f}%',
        'Matinee %': '{:.1f}%',
        'Evening %': '{:.1f}%',
        'Late %': '{:.1f}%',
        'Avg $ General': '${:.2f}',
        'Avg $ Child': '${:.2f}',
        'Avg $ Senior': '${:.2f}'
    }
    
    # Apply formatting
    styled_df = display_df.style.format(format_dict, na_rep='-')
    
    # Highlight Marcus row
    def highlight_marcus(row):
        if 'Marcus' in str(row['Circuit']):
            return ['background-color: #FFF3CD'] * len(row)
        return [''] * len(row)
    
    styled_df = styled_df.apply(highlight_marcus, axis=1)
    
    st.dataframe(styled_df, use_container_width=True, height=500)


def render_format_tab(df: pd.DataFrame):
    """Render format mix analysis"""
    st.subheader("Format Mix Comparison")
    
    # Create format breakdown DataFrame
    format_df = df[['circuit_name', 'format_imax_pct', 'format_dolby_pct', 
                     'format_3d_pct', 'format_other_premium_pct', 'format_standard_pct']].copy()
    format_df.columns = ['Circuit', 'IMAX', 'Dolby', '3D', 'Other Premium', 'Standard']
    
    # Bar chart
    import altair as alt
    
    # Reshape for stacked bar chart
    format_melted = format_df.melt(id_vars=['Circuit'], 
                                     var_name='Format', 
                                     value_name='Percentage')
    
    chart = alt.Chart(format_melted).mark_bar().encode(
        x=alt.X('Circuit:N', sort='-y', axis=alt.Axis(labelAngle=-45)),
        y=alt.Y('Percentage:Q', title='Percentage of Showtimes'),
        color=alt.Color('Format:N', scale=alt.Scale(scheme='tableau10')),
        tooltip=['Circuit:N', 'Format:N', alt.Tooltip('Percentage:Q', format='.1f')]
    ).properties(
        height=400
    )
    
    st.altair_chart(chart, use_container_width=True)
    
    # PLF penetration comparison
    st.subheader("PLF Penetration Analysis")
    
    plf_df = df[['circuit_name', 'plf_total_pct']].copy()
    plf_df.columns = ['Circuit', 'Total PLF %']
    plf_df = plf_df.sort_values('Total PLF %', ascending=False)
    
    # Highlight Marcus
    marcus_plf = plf_df[plf_df['Circuit'].str.contains('Marcus', case=False)]['Total PLF %'].values
    avg_plf = plf_df['Total PLF %'].mean()
    
    col1, col2 = st.columns(2)
    
    with col1:
        if len(marcus_plf) > 0:
            st.metric("Marcus PLF Penetration", f"{marcus_plf[0]:.1f}%")
    with col2:
        st.metric("Top 10 Average", f"{avg_plf:.1f}%", 
                 delta=f"{marcus_plf[0] - avg_plf:+.1f}%" if len(marcus_plf) > 0 else None)
    
    st.dataframe(plf_df.style.format({'Total PLF %': '{:.1f}%'}), 
                use_container_width=True, hide_index=True)


def render_daypart_tab(df: pd.DataFrame):
    """Render daypart strategy analysis"""
    st.subheader("Daypart Strategy Comparison")
    
    # Create daypart DataFrame
    daypart_df = df[['circuit_name', 'daypart_matinee_pct', 
                      'daypart_evening_pct', 'daypart_late_pct']].copy()
    daypart_df.columns = ['Circuit', 'Matinee', 'Evening', 'Late Night']
    
    # Stacked bar chart
    import altair as alt
    
    daypart_melted = daypart_df.melt(id_vars=['Circuit'], 
                                      var_name='Daypart', 
                                      value_name='Percentage')
    
    chart = alt.Chart(daypart_melted).mark_bar().encode(
        x=alt.X('Circuit:N', sort='-y', axis=alt.Axis(labelAngle=-45)),
        y=alt.Y('Percentage:Q', title='Percentage of Showtimes', stack='normalize'),
        color=alt.Color('Daypart:N', scale=alt.Scale(scheme='goldorange')),
        tooltip=['Circuit:N', 'Daypart:N', alt.Tooltip('Percentage:Q', format='.1f')]
    ).properties(
        height=400
    )
    
    st.altair_chart(chart, use_container_width=True)
    
    # Detailed table
    st.dataframe(daypart_df.style.format({
        'Matinee': '{:.1f}%',
        'Evening': '{:.1f}%',
        'Late Night': '{:.1f}%'
    }), use_container_width=True, hide_index=True)
    
    # Marcus comparison
    marcus_data = daypart_df[daypart_df['Circuit'].str.contains('Marcus', case=False)]
    if not marcus_data.empty:
        st.subheader("Marcus vs Industry Average")
        
        marcus_row = marcus_data.iloc[0]
        avg_matinee = daypart_df['Matinee'].mean()
        avg_evening = daypart_df['Evening'].mean()
        avg_late = daypart_df['Late Night'].mean()
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Matinee", f"{marcus_row['Matinee']:.1f}%", 
                     delta=f"{marcus_row['Matinee'] - avg_matinee:+.1f}% vs avg")
        with col2:
            st.metric("Evening", f"{marcus_row['Evening']:.1f}%", 
                     delta=f"{marcus_row['Evening'] - avg_evening:+.1f}% vs avg")
        with col3:
            st.metric("Late Night", f"{marcus_row['Late Night']:.1f}%", 
                     delta=f"{marcus_row['Late Night'] - avg_late:+.1f}% vs avg")


def render_pricing_tab(df: pd.DataFrame):
    """Render pricing analysis"""
    st.subheader("Pricing Comparison")
    
    # Filter circuits with pricing data
    pricing_df = df[df['avg_price_general'].notna()][
        ['circuit_name', 'avg_price_general', 'avg_price_child', 'avg_price_senior']
    ].copy()
    
    if pricing_df.empty:
        st.info("⚠️ Pricing data not available from EntTelligence API")
        return
    
    pricing_df.columns = ['Circuit', 'General', 'Child', 'Senior']
    pricing_df = pricing_df.sort_values('General', ascending=False)
    
    # Metrics
    marcus_pricing = pricing_df[pricing_df['Circuit'].str.contains('Marcus', case=False)]
    avg_general = pricing_df['General'].mean()
    
    if not marcus_pricing.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Marcus Avg Price (General)", 
                     f"${marcus_pricing.iloc[0]['General']:.2f}")
        with col2:
            delta = marcus_pricing.iloc[0]['General'] - avg_general
            st.metric("vs Top 10 Average", 
                     f"${delta:+.2f}",
                     help=f"Industry avg: ${avg_general:.2f}")
    
    # Pricing table
    st.dataframe(pricing_df.style.format({
        'General': '${:.2f}',
        'Child': '${:.2f}',
        'Senior': '${:.2f}'
    }), use_container_width=True, hide_index=True)
    
    # Bar chart
    import altair as alt
    
    chart = alt.Chart(pricing_df).mark_bar().encode(
        x=alt.X('Circuit:N', sort='-y', axis=alt.Axis(labelAngle=-45)),
        y=alt.Y('General:Q', title='Average General Admission Price ($)'),
        color=alt.condition(
            alt.datum.Circuit.indexOf('Marcus') >= 0,
            alt.value('#FFD700'),  # Gold for Marcus
            alt.value('steelblue')
        ),
        tooltip=['Circuit:N', alt.Tooltip('General:Q', format='$.2f')]
    ).properties(
        height=400
    )
    
    st.altair_chart(chart, use_container_width=True)


def generate_excel_report(week_ending_date: str) -> bytes:
    """
    Generate Excel workbook matching Top 10 Report structure.
    Ready for copy/paste into existing reports.
    """
    df = load_circuit_data(week_ending_date)
    
    if df.empty:
        return None
    
    # Create Excel writer
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        
        # Sheet 1: Overview (matches report structure)
        overview = df[[
            'circuit_name', 'total_showtimes', 'total_theaters', 
            'total_films', 'avg_screens_per_film', 'avg_showtimes_per_theater'
        ]].copy()
        overview.columns = ['Circuit', 'Total Showtimes', 'Theaters', 
                           'Films', 'Screens/Film', 'Shows/Theater']
        overview.to_excel(writer, sheet_name='Overview', index=False)
        
        # Sheet 2: Format Mix
        format_mix = df[[
            'circuit_name', 'format_imax_pct', 'format_dolby_pct', 
            'format_3d_pct', 'format_other_premium_pct', 'format_standard_pct',
            'plf_total_pct'
        ]].copy()
        format_mix.columns = ['Circuit', 'IMAX %', 'Dolby %', '3D %', 
                             'Other Premium %', 'Standard %', 'Total PLF %']
        format_mix.to_excel(writer, sheet_name='Format Mix', index=False)
        
        # Sheet 3: Daypart Strategy
        daypart = df[[
            'circuit_name', 'daypart_matinee_pct', 
            'daypart_evening_pct', 'daypart_late_pct'
        ]].copy()
        daypart.columns = ['Circuit', 'Matinee %', 'Evening %', 'Late Night %']
        daypart.to_excel(writer, sheet_name='Daypart Strategy', index=False)
        
        # Sheet 4: Pricing (if available)
        if df['avg_price_general'].notna().any():
            pricing = df[[
                'circuit_name', 'avg_price_general', 
                'avg_price_child', 'avg_price_senior'
            ]].copy()
            pricing.columns = ['Circuit', 'Avg Price (General)', 
                              'Avg Price (Child)', 'Avg Price (Senior)']
            pricing.to_excel(writer, sheet_name='Pricing', index=False)
        
        # Sheet 5: Marcus vs Top 10 Summary
        marcus_data = df[df['circuit_name'].str.contains('Marcus', case=False)]
        if not marcus_data.empty:
            marcus_row = marcus_data.iloc[0]
            
            summary_data = {
                'Metric': [
                    'Total Showtimes',
                    'Total Theaters',
                    'PLF Penetration %',
                    'IMAX %',
                    'Dolby %',
                    'Matinee %',
                    'Evening %',
                    'Screens per Film'
                ],
                'Marcus': [
                    marcus_row['total_showtimes'],
                    marcus_row['total_theaters'],
                    marcus_row['plf_total_pct'],
                    marcus_row['format_imax_pct'],
                    marcus_row['format_dolby_pct'],
                    marcus_row['daypart_matinee_pct'],
                    marcus_row['daypart_evening_pct'],
                    marcus_row['avg_screens_per_film']
                ],
                'Top 10 Average': [
                    df['total_showtimes'].mean(),
                    df['total_theaters'].mean(),
                    df['plf_total_pct'].mean(),
                    df['format_imax_pct'].mean(),
                    df['format_dolby_pct'].mean(),
                    df['daypart_matinee_pct'].mean(),
                    df['daypart_evening_pct'].mean(),
                    df['avg_screens_per_film'].mean()
                ]
            }
            
            summary_df = pd.DataFrame(summary_data)
            summary_df['Difference'] = summary_df['Marcus'] - summary_df['Top 10 Average']
            summary_df['% Difference'] = (summary_df['Difference'] / summary_df['Top 10 Average'] * 100)
            
            summary_df.to_excel(writer, sheet_name='Marcus vs Top 10', index=False)
    
    output.seek(0)
    return output.getvalue()
