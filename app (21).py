# app.py
from flask import Flask, render_template, request, jsonify
import sqlite3
import math
import requests
import json
from datetime import datetime, timedelta
import os
import ast

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'

# Initialize database
def init_db():
    conn = sqlite3.connect('solar_data.db')
    c = conn.cursor()
    
    # Create tables
    c.execute('''CREATE TABLE IF NOT EXISTS appliances
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  wattage REAL NOT NULL,
                  hours_per_day REAL NOT NULL,
                  quantity INTEGER DEFAULT 1,
                  user_session TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS solar_calculations
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_session TEXT,
                  latitude REAL,
                  longitude REAL,
                  total_daily_consumption REAL,
                  panels_needed INTEGER,
                  battery_capacity REAL,
                  system_cost REAL,
                  payback_period REAL,
                  co2_savings REAL,
                  calculation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    conn.commit()
    conn.close()

# Solar calculation functions
def calculate_panel_requirements(appliances_data):
    total_daily_wh = 0
    for appliance in appliances_data:
        # accept both 'hours' and 'hours_per_day' keys
        hours = appliance.get('hours') or appliance.get('hours_per_day') or 0
        quantity = appliance.get('quantity', 1)
        wattage = appliance.get('wattage', 0)
        daily_consumption = wattage * hours * quantity
        total_daily_wh += daily_consumption
    
    # Convert to kWh
    total_daily_kwh = total_daily_wh / 1000 if total_daily_wh else 0
    
    # Assume 300W panels, 4-5 hours of peak sun, system efficiency 85%
    panel_output_per_day = 0.3 * 4.5 * 0.85  # kWh per panel per day
    panels_needed = math.ceil(total_daily_kwh / panel_output_per_day) if panel_output_per_day > 0 else 0
    
    return {
        'total_daily_wh': round(total_daily_wh, 2),
        'total_daily_kwh': round(total_daily_kwh, 3),
        'panels_needed': panels_needed,
        'recommended_system_size': round(panels_needed * 0.3, 2)
    }

def calculate_optimal_tilt_angle(latitude):
    # Basic formula for optimal tilt angle
    try:
        lat = float(latitude)
    except:
        lat = 0.0
    if abs(lat) < 25:
        optimal_angle = abs(lat)
    else:
        optimal_angle = abs(lat) * 0.87 + 3.1
    
    # Seasonal adjustments
    winter_angle = optimal_angle + 15
    summer_angle = max(0, optimal_angle - 15)
    
    return {
        'optimal_angle': round(optimal_angle, 1),
        'winter_angle': round(winter_angle, 1),
        'summer_angle': round(summer_angle, 1)
    }

def estimate_solar_production(latitude, longitude, system_size_kw, tilt_angle=None):
    # Use NASA POWER API for solar data
    try:
        url = "https://power.larc.nasa.gov/api/temporal/daily/point"
        params = {
            'parameters': 'ALLSKY_SFC_SW_DWN',
            'community': 'RE',
            'longitude': longitude,
            'latitude': latitude,
            'start': '20230101',
            'end': '20231231',
            'format': 'JSON'
        }
        
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            solar_values = list(data['properties']['parameter']['ALLSKY_SFC_SW_DWN'].values())
            avg_solar_irradiance = sum(solar_values) / len(solar_values) if solar_values else 4.5
        else:
            avg_solar_irradiance = 4.5  # Default fallback
    except Exception:
        avg_solar_irradiance = 4.5  # Default fallback
    
    # Calculate daily production (kWh)
    system_efficiency = 0.85  # Account for inverter losses, wiring, etc.
    # avg_solar_irradiance is in W/m2 daily totals; convert to approximate peak sun hours:
    # Use simplified approach: treat avg_solar_irradiance/1000 as average kW/m2 over day, multiply by 24 -> not perfect,
    # previous code used conversion to peak sun hours as avg_solar_irradiance / 1000 * 24
    # Keep the same approach (fallback to typical 4.5 if data missing)
    peak_sun_hours = avg_solar_irradiance / 1000 * 24
    
    daily_production = system_size_kw * peak_sun_hours * system_efficiency
    weekly_production = daily_production * 7
    monthly_production = daily_production * 30
    
    return {
        'daily_kwh': round(daily_production, 2),
        'weekly_kwh': round(weekly_production, 2),
        'monthly_kwh': round(monthly_production, 2),
        'yearly_kwh': round(daily_production * 365, 2),
        'peak_sun_hours': round(peak_sun_hours, 2)
    }

def calculate_battery_sizing(daily_consumption_kwh, backup_days=2):
    # Battery sizing with depth of discharge consideration
    usable_capacity = daily_consumption_kwh * backup_days
    # Assuming 80% depth of discharge for lithium batteries
    total_battery_capacity = usable_capacity / 0.8 if usable_capacity > 0 else 0
    
    return {
        'recommended_capacity_kwh': round(total_battery_capacity, 2),
        'backup_days': backup_days,
        'estimated_cost': round(total_battery_capacity * 500, 2)  # $500 per kWh estimate
    }

def calculate_cost_and_roi(system_size_kw, battery_capacity_kwh, monthly_consumption_kwh):
    # Cost estimates (USD)
    panel_cost_per_kw = 1000  # $1000 per kW
    inverter_cost = system_size_kw * 200  # $200 per kW
    installation_cost = system_size_kw * 300  # $300 per kW
    battery_cost = battery_capacity_kwh * 500  # $500 per kWh
    
    total_system_cost = (system_size_kw * panel_cost_per_kw) + inverter_cost + installation_cost + battery_cost
    
    # ROI calculation
    electricity_rate = 0.12  # $0.12 per kWh
    monthly_savings = monthly_consumption_kwh * electricity_rate
    yearly_savings = monthly_savings * 12
    
    payback_period = total_system_cost / yearly_savings if yearly_savings > 0 else 0
    
    return {
        'total_cost': round(total_system_cost, 2),
        'panel_cost': round(system_size_kw * panel_cost_per_kw, 2),
        'inverter_cost': round(inverter_cost, 2),
        'installation_cost': round(installation_cost, 2),
        'battery_cost': round(battery_cost, 2),
        'monthly_savings': round(monthly_savings, 2),
        'yearly_savings': round(yearly_savings, 2),
        'payback_period_years': round(payback_period, 1)
    }

def calculate_co2_savings(yearly_production_kwh):
    # CO2 emission factor for grid electricity (kg CO2 per kWh)
    co2_factor = 0.5  # Average global factor
    yearly_co2_savings = yearly_production_kwh * co2_factor
    
    return {
        'yearly_co2_savings_kg': round(yearly_co2_savings, 2),
        'yearly_co2_savings_tons': round(yearly_co2_savings / 1000, 2),
        'equivalent_trees_planted': round(yearly_co2_savings / 22, 0)  # 1 tree absorbs ~22kg CO2/year
    }

def calculate_degradation_forecast(initial_production, years=25):
    degradation_rate = 0.005  # 0.5% per year
    forecast = []
    
    for year in range(1, years + 1):
        remaining_efficiency = (1 - degradation_rate) ** year
        production = initial_production * remaining_efficiency
        forecast.append({
            'year': year,
            'production_kwh': round(production, 2),
            'efficiency_percent': round(remaining_efficiency * 100, 1)
        })
    
    return forecast

# --- Routes
@app.route('/api/calculate', methods=['POST'])
def calculate_solar_system():
    data = request.get_json()
    
    # Extract data
    appliances = data.get('appliances', [])
    latitude = float(data.get('latitude', 0))
    longitude = float(data.get('longitude', 0))
    budget = data.get('budget', 10000)
    
    # Perform calculations
    panel_req = calculate_panel_requirements(appliances)
    tilt_angles = calculate_optimal_tilt_angle(latitude)
    production = estimate_solar_production(latitude, longitude, panel_req['recommended_system_size'])
    battery = calculate_battery_sizing(panel_req['total_daily_kwh'])
    cost_roi = calculate_cost_and_roi(panel_req['recommended_system_size'], battery['recommended_capacity_kwh'], panel_req['total_daily_kwh'] * 30)
    co2_savings = calculate_co2_savings(production['yearly_kwh'])
    degradation = calculate_degradation_forecast(production['yearly_kwh'])
    
    # Grid dependency analysis
    daily_production = production['daily_kwh']
    daily_consumption = panel_req['total_daily_kwh']
    
    if daily_production >= daily_consumption and daily_consumption > 0:
        grid_import = 0
        excess_export = daily_production - daily_consumption
        self_consumption_percent = 100.0
    else:
        grid_import = max(0, daily_consumption - daily_production)
        excess_export = 0
        self_consumption_percent = (daily_production / daily_consumption) * 100 if daily_consumption > 0 else 0
    
    grid_analysis = {
        'daily_grid_import_kwh': round(grid_import, 2),
        'daily_excess_export_kwh': round(excess_export, 2),
        'self_consumption_percent': round(self_consumption_percent, 1),
        'grid_dependency_percent': round(100 - self_consumption_percent, 1)
    }
    
    # System comparison (3kW vs 5kW vs optimal)
    comparison = []
    for system_size in [3, 5, panel_req['recommended_system_size']]:
        sys_production = estimate_solar_production(latitude, longitude, system_size)
        sys_cost = calculate_cost_and_roi(system_size, battery['recommended_capacity_kwh'] * 0.7, panel_req['total_daily_kwh'] * 30)
        
        comparison.append({
            'system_size_kw': system_size,
            'yearly_production_kwh': sys_production['yearly_kwh'],
            'total_cost': sys_cost['total_cost'],
            'payback_period': sys_cost['payback_period_years']
        })
    
    # Maintenance schedule
    maintenance = {
        'panel_cleaning': 'Every 3-6 months',
        'inverter_replacement': '10-15 years',
        'battery_replacement': '8-12 years',
        'system_inspection': 'Annual'
    }
    
    result = {
        'panel_requirements': panel_req,
        'tilt_angles': tilt_angles,
        'production_estimate': production,
        'battery_sizing': battery,
        'cost_roi': cost_roi,
        'co2_savings': co2_savings,
        'grid_analysis': grid_analysis,
        'degradation_forecast': degradation[:10],  # First 10 years
        'system_comparison': comparison,
        'maintenance_schedule': maintenance
    }
    
    return jsonify(result)

@app.route('/api/weather', methods=['POST'])
def get_weather_data():
    data = request.get_json()
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    
    try:
        # OpenWeatherMap free API (you'll need to get a free API key)
        api_key = os.environ.get('OPENWEATHER_API_KEY', 'your_free_api_key_here')
        url = f"http://api.openweathermap.org/data/2.5/weather?lat={latitude}&lon={longitude}&appid={api_key}&units=metric"
        
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            weather_data = response.json()
            return jsonify({
                'current_weather': {
                    'temperature': weather_data['main']['temp'],
                    'humidity': weather_data['main']['humidity'],
                    'cloudiness': weather_data['clouds']['all'],
                    'description': weather_data['weather'][0]['description']
                },
                'solar_adjustment': max(0.3, 1 - (weather_data['clouds']['all'] / 100))
            })
    except Exception:
        pass
    
    return jsonify({
        'current_weather': {
            'temperature': 25,
            'humidity': 60,
            'cloudiness': 30,
            'description': 'partly cloudy'
        },
        'solar_adjustment': 0.8
    })

# --- Serve the full HTML page (front-end) ---
@app.route('/')
def index():
    # We return a big HTML string (keeps everything in a single file)
    # This HTML is based on your original layout and CSS, with JS fixes:
    html_content = r'''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Solar Energy Calculator & Monitor</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.9.1/chart.min.js"></script>
<style>
/* --- full CSS preserved from original --- */
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; color: #333; }
.container { max-width: 1200px; margin: 0 auto; padding: 20px; }
.header { text-align: center; color: white; margin-bottom: 30px; }
.header h1 { font-size: 2.5rem; margin-bottom: 10px; }
.header p { font-size: 1.1rem; opacity: 0.9; }
.dashboard { display: grid; grid-template-columns: 1fr 2fr; gap: 20px; margin-bottom: 30px; }
.input-panel, .results-panel { background: white; border-radius: 15px; padding: 25px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }
.section-title { font-size: 1.4rem; color: #4a5568; margin-bottom: 20px; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; }
.form-group { margin-bottom: 20px; }
label { display: block; margin-bottom: 5px; font-weight: 600; color: #4a5568; }
input, select { width: 100%; padding: 12px; border: 2px solid #e2e8f0; border-radius: 8px; font-size: 1rem; transition: border-color 0.3s; }
input:focus, select:focus { outline: none; border-color: #667eea; }
.appliance-item { background: #f7fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 15px; margin-bottom: 10px; }
.appliance-row { display: grid; grid-template-columns: 2fr 1fr 1fr 1fr auto; gap: 10px; align-items: center; }
.btn { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; padding: 12px 24px; border-radius: 8px; font-size: 1rem; font-weight: 600; cursor: pointer; transition: transform 0.2s, box-shadow 0.2s; }
.btn:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(0,0,0,0.2); }
.btn-secondary { background: #e2e8f0; color: #4a5568; }
.btn-danger { background: #e53e3e; color: white; }
.btn-small { padding: 8px 16px; font-size: 0.9rem; }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 30px; }
.stat-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 12px; text-align: center; }
.stat-value { font-size: 2rem; font-weight: bold; margin-bottom: 5px; }
.stat-label { font-size: 0.9rem; opacity: 0.9; }
.chart-container { background: white; border-radius: 15px; padding: 25px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); margin-bottom: 20px; }
.tabs { display: flex; border-bottom: 1px solid #e2e8f0; margin-bottom: 20px; }
.tab { padding: 12px 24px; cursor: pointer; border-bottom: 2px solid transparent; font-weight: 600; transition: all 0.3s; }
.tab.active { color: #667eea; border-bottom-color: #667eea; }
.tab:hover:not([aria-selected="true"]) { transform: translateY(-1px); }
.loading { text-align: center; padding: 40px; color: #718096; }
.spinner { border: 4px solid #e2e8f0; border-top: 4px solid #667eea; border-radius: 50%; width: 50px; height: 50px; animation: spin 1s linear infinite; margin: 0 auto 20px; }
@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
.info-card { background: #f0f8ff; border: 1px solid #0066cc; border-radius: 8px; padding: 15px; margin: 10px 0; }
.maintenance-item { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #e2e8f0; }
@media (max-width: 768px) { .dashboard { grid-template-columns: 1fr; } .appliance-row { grid-template-columns: 1fr; gap: 5px; } .stats-grid { grid-template-columns: 1fr; } }
/* Remove number input arrows */
input[type=number]::-webkit-inner-spin-button, 
input[type=number]::-webkit-outer-spin-button {
    -webkit-appearance: none;
    margin: 0;
}

input[type=number] {
    -moz-appearance: textfield; /* For Firefox */
}

</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>☀️ Solar Energy Calculator</h1>
        <p>Complete solar system calculator with monitoring and analysis</p>
    </div>

    <div class="dashboard">
        <div class="input-panel">
            <h2 class="section-title">System Configuration</h2>
            
            <div class="form-group">
                <label>Latitude</label>
                <input type="number" id="latitude" placeholder="31.4504 (Faisalabad)" step="0.0001" value="31.4504">
            </div>
            
            <div class="form-group">
                <label>Longitude</label>
                <input type="number" id="longitude" placeholder="73.1350 (Faisalabad)" step="0.0001" value="73.1350">
            </div>
            
            <div class="form-group">
                <label>Budget (USD)</label>
                <input type="number" id="budget" placeholder="10000" min="0" value="10000">
            </div>

            <h3 style="margin: 20px 0 10px 0; color: #4a5568;">Appliances</h3>
            <div id="appliances-list"></div>
            
            <button class="btn btn-secondary" onclick="addAppliance()">+ Add Appliance</button>
            <button class="btn" onclick="calculateSystem()" style="margin-left: 10px;">Calculate System</button>
            
            <div style="margin-top: 20px;">
                <button class="btn btn-secondary" onclick="loadSampleData()">Load Sample Home</button>
            </div>
        </div>

        <div class="results-panel">
            <h2 class="section-title">System Overview</h2>
            <div id="loading" class="loading" style="display: none;">
                <div class="spinner"></div>
                <p>Calculating your solar system...</p>
            </div>
            
            <div id="results" style="display: none;">
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-value" id="panels-needed">0</div>
                        <div class="stat-label">Solar Panels</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="system-size">0</div>
                        <div class="stat-label">System Size (kW)</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="yearly-production">0</div>
                        <div class="stat-label">Yearly kWh</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="payback-period">0</div>
                        <div class="stat-label">Payback Years</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div class="chart-container">
        <div class="tabs">
            <div class="tab active" onclick="showTab('production', event)">Production</div>
            <div class="tab" onclick="showTab('cost', event)">Cost Analysis</div>
            <div class="tab" onclick="showTab('environmental', event)">Environmental</div>
            <div class="tab" onclick="showTab('grid', event)">Grid Analysis</div>
        </div>

        <div id="production-tab" class="tab-content active">
            <h3 style="margin-bottom: 20px; color: #4a5568;">Energy Production & Consumption</h3>
            <canvas id="productionChart" width="400" height="200"></canvas>
            <div id="production-details" style="margin-top: 20px;"></div>
        </div>

        <div id="cost-tab" class="tab-content">
            <h3 style="margin-bottom: 20px; color: #4a5568;">Cost Breakdown & ROI</h3>
            <canvas id="costChart" width="400" height="200"></canvas>
            <div id="roi-details" style="margin-top: 20px;"></div>
        </div>

        <div id="environmental-tab" class="tab-content">
            <h3 style="margin-bottom: 20px; color: #4a5568;">Environmental Impact</h3>
            <div id="environmental-details"></div>
            <canvas id="environmentalChart" width="400" height="200"></canvas>
        </div>
 

        <div id="grid-tab" class="tab-content">
            <h3 style="margin-bottom: 20px; color: #4a5568;">Grid Dependency Analysis</h3>
            <canvas id="gridChart" width="400" height="200"></canvas>
            <div id="grid-details" style="margin-top: 20px;"></div>
        </div>
    </div>

    <div class="chart-container">
        <div class="tabs">
            <div class="tab active" onclick="showDetailTab('tilt', event)">Optimal Tilt</div>
            <div class="tab" onclick="showDetailTab('comparison', event)">System Sizes</div>
            <div class="tab" onclick="showDetailTab('maintenance', event)">Maintenance</div>
            <div class="tab" onclick="showDetailTab('degradation', event)">Degradation</div>
        </div>

        <div id="tilt-detail" class="tab-content active">
            <div id="tilt-info">
                <div class="info-card">
                    <h4>Panel Positioning Guide</h4>
                    <p>Click "Calculate System" to see optimal tilt angles for your location.</p>
                </div>
            </div>
        </div>

        <div id="comparison-detail" class="tab-content">
            <canvas id="comparisonChart" width="400" height="200"></canvas>
            <div id="comparison-details" style="margin-top: 20px;"></div>
        </div>

        <div id="maintenance-detail" class="tab-content">
            <div id="maintenance-info">
                <div class="info-card">
                    <h4>Maintenance Guidelines</h4>
                    <p>Click "Calculate System" to see personalized maintenance schedule.</p>
                </div>
            </div>
        </div>

        <div id="degradation-detail" class="tab-content">
            <canvas id="degradationChart" width="400" height="200"></canvas>
        </div>
    </div>
</div>

<script>
    let applianceCount = 0;
    let charts = {};
    let calculationResults = null;
    
    function loadSampleData() {
        document.getElementById('appliances-list').innerHTML = '';
        applianceCount = 0;
        
        const sampleAppliances = [
            {name: 'LED Lights', wattage: 60, hours: 8, quantity: 10},
            {name: 'Refrigerator', wattage: 150, hours: 24, quantity: 1},
            {name: 'Air Conditioner', wattage: 1500, hours: 8, quantity: 2},
            {name: 'Washing Machine', wattage: 500, hours: 2, quantity: 1},
            {name: 'TV', wattage: 100, hours: 6, quantity: 2},
            {name: 'Fan', wattage: 75, hours: 12, quantity: 5},
            {name: 'Water Pump', wattage: 750, hours: 2, quantity: 1}
        ];
        
        sampleAppliances.forEach(appliance => {
            addAppliance();
            document.getElementById('name-' + applianceCount).value = appliance.name;
            document.getElementById('wattage-' + applianceCount).value = appliance.wattage;
            document.getElementById('hours-' + applianceCount).value = appliance.hours;
            document.getElementById('quantity-' + applianceCount).value = appliance.quantity;
        });
    }
    
    function addAppliance() {
        applianceCount++;
        const appliancesList = document.getElementById('appliances-list');
        const applianceItem = document.createElement('div');
        applianceItem.className = 'appliance-item';
        applianceItem.id = 'appliance-' + applianceCount;
        
        applianceItem.innerHTML = `
        <div class="appliance-row" style="display: grid; grid-template-columns: 30px 2fr 1fr 1fr 1fr auto; gap: 10px; align-items: center;">
            <input type="checkbox" id="check-${applianceCount}" checked>
            <input type="text" placeholder="Appliance Name" id="name-${applianceCount}" style="padding: 5px;">
            <input type="number" placeholder="Watts" id="wattage-${applianceCount}" min="0" style="padding: 5px;">
            <input type="number" placeholder="Hours/day" id="hours-${applianceCount}" min="0" step="0.1" style="padding: 5px;">
            <input type="number" placeholder="Quantity" id="quantity-${applianceCount}" min="1" value="1" style="padding: 5px;">
            <button class="btn btn-danger btn-small" onclick="removeAppliance(${applianceCount})">×</button>
        </div>`;



        
        appliancesList.appendChild(applianceItem);
    }
    
    function removeAppliance(id) {
        const appliance = document.getElementById('appliance-' + id);
        if (appliance) {
            appliance.remove();
        }
    }
    
    function getAppliancesData() {
        const appliances = [];
        const applianceItems = document.querySelectorAll('.appliance-item');
        
        applianceItems.forEach(function(item) {
            const id = item.id.split('-')[1];
            const name = document.getElementById('name-' + id).value || '';
            const wattage = parseFloat(document.getElementById('wattage-' + id).value) || 0;
            const hours = parseFloat(document.getElementById('hours-' + id).value) || 0;
            const quantity = parseInt(document.getElementById('quantity-' + id).value) || 1;
            
            if (name && wattage > 0 && hours > 0) {
                appliances.push({
                    name: name,
                    wattage: wattage,
                    hours: hours,
                    quantity: quantity
                });
            }
        });
        
        return appliances;
    }
    
    async function calculateSystem() {
        const appliances = getAppliancesData();
        const latitude = parseFloat(document.getElementById('latitude').value);
        const longitude = parseFloat(document.getElementById('longitude').value);
        const budget = parseFloat(document.getElementById('budget').value) || 10000;
        
        if (appliances.length === 0) {
            alert('Please add at least one appliance');
            return;
        }
        
        if (!latitude || !longitude) {
            alert('Please enter valid latitude and longitude');
            return;
        }
        
        document.getElementById('loading').style.display = 'block';
        document.getElementById('results').style.display = 'none';
        
        try {
            const response = await fetch('/api/calculate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    appliances: appliances,
                    latitude: latitude,
                    longitude: longitude,
                    budget: budget
                })
            });
            
            if (!response.ok) throw new Error('Calculation failed');
            
            calculationResults = await response.json();
            displayResults(calculationResults);
            
        } catch (error) {
            console.error('Error:', error);
            alert('Error calculating system. Please try again.');
        } finally {
            document.getElementById('loading').style.display = 'none';
        }
    }
    
    function displayResults(data) {
        document.getElementById('results').style.display = 'block';
        
        document.getElementById('panels-needed').textContent = data.panel_requirements.panels_needed;
        document.getElementById('system-size').textContent = data.panel_requirements.recommended_system_size.toFixed(1) + 'kW';
        document.getElementById('yearly-production').textContent = data.production_estimate.yearly_kwh;
        document.getElementById('payback-period').textContent = data.cost_roi.payback_period_years;
        
        updateCharts(data);
        updateDetailedInfo(data);
    }
    
    function updateCharts(data) {
        updateProductionChart(data);
        updateCostChart(data);
        updateEnvironmentalChart(data);
        updateGridChart(data);
        updateComparisonChart(data);
        updateDegradationChart(data);
    }
    
    function updateProductionChart(data) {
        const ctx = document.getElementById('productionChart').getContext('2d');
        
        if (charts.production) charts.production.destroy();
        
        charts.production = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['Daily', 'Weekly', 'Monthly', 'Yearly'],
                datasets: [{
                    label: 'Production (kWh)',
                    data: [
                        data.production_estimate.daily_kwh,
                        data.production_estimate.weekly_kwh,
                        data.production_estimate.monthly_kwh,
                        data.production_estimate.yearly_kwh
                    ],
                    backgroundColor: 'rgba(102, 126, 234, 0.6)',
                    borderColor: 'rgba(102, 126, 234, 1)',
                    borderWidth: 2
                }, {
                    label: 'Consumption (kWh)',
                    data: [
                        data.panel_requirements.total_daily_kwh,
                        data.panel_requirements.total_daily_kwh * 7,
                        data.panel_requirements.total_daily_kwh * 30,
                        data.panel_requirements.total_daily_kwh * 365
                    ],
                    backgroundColor: 'rgba(231, 76, 60, 0.6)',
                    borderColor: 'rgba(231, 76, 60, 1)',
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: {
                        position: 'top'
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Energy (kWh)'
                        }
                    }
                }
            }
        });
        
        document.getElementById('production-details').innerHTML = 
            '<div class="info-card">' +
            '<h4>Production Summary</h4>' +
            '<p><strong>Peak Sun Hours:</strong> ' + data.production_estimate.peak_sun_hours + ' hours/day</p>' +
            '<p><strong>Optimal Tilt Angle:</strong> ' + data.tilt_angles.optimal_angle + '°</p>' +
            '<p><strong>Winter Adjustment:</strong> ' + data.tilt_angles.winter_angle + '°</p>' +
            '<p><strong>Summer Adjustment:</strong> ' + data.tilt_angles.summer_angle + '°</p>' +
            '</div>';
    }
    
    function updateCostChart(data) {
        const ctx = document.getElementById('costChart').getContext('2d');
        
        if (charts.cost) charts.cost.destroy();
        
        charts.cost = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Panels', 'Inverter', 'Installation', 'Battery'],
                datasets: [{
                    data: [
                        data.cost_roi.panel_cost,
                        data.cost_roi.inverter_cost,
                        data.cost_roi.installation_cost,
                        data.cost_roi.battery_cost
                    ],
                    backgroundColor: [
                        'rgba(102, 126, 234, 0.8)',
                        'rgba(46, 204, 113, 0.8)',
                        'rgba(241, 196, 15, 0.8)',
                        'rgba(231, 76, 60, 0.8)'
                    ]
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: {
                        position: 'right'
                    }
                }
            }
        });
        
        document.getElementById('roi-details').innerHTML = 
            '<div class="info-card">' +
            `<h4>Investment Analysis</h4>
            <p><strong>Total System Cost:</strong> ${data.cost_roi.total_cost.toLocaleString()}</p>
            <p><strong>Monthly Savings:</strong> ${data.cost_roi.monthly_savings}</p>
            <p><strong>Yearly Savings:</strong> ${data.cost_roi.yearly_savings}</p>
            <p><strong>Payback Period:</strong> ${data.cost_roi.payback_period_years} years</p>
            <p><strong>Battery Capacity:</strong> ${data.battery_sizing.recommended_capacity_kwh} kWh</p>` +
            '</div>';
    }
    
    function updateEnvironmentalChart(data) {
        document.getElementById('environmental-details').innerHTML = 
            '<div class="info-card">' +
            '<h4>🌱 Environmental Benefits</h4>' +
            '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0;">' +
            '<div style="text-align: center; background: #e8f5e8; padding: 15px; border-radius: 8px;">' +
            '<div style="font-size: 2rem; color: #27ae60; font-weight: bold;">' + data.co2_savings.yearly_co2_savings_tons + '</div>' +
            '<div>Tons CO₂ Saved/Year</div>' +
            '</div>' +
            '<div style="text-align: center; background: #e8f5e8; padding: 15px; border-radius: 8px;">' +
            '<div style="font-size: 2rem; color: #27ae60; font-weight: bold;">' + data.co2_savings.equivalent_trees_planted + '</div>' +
            '<div>Equivalent Trees Planted</div>' +
            '</div>' +
            '</div>' +
            '</div>';
        
        const ctx = document.getElementById('environmentalChart').getContext('2d');
        if (charts.environmental) charts.environmental.destroy();
        
        const years = Array.from({length: 25}, function(_, i) { return i + 1; });
        const cumulativeCO2 = years.map(function(year) { return data.co2_savings.yearly_co2_savings_tons * year; });
        
        charts.environmental = new Chart(ctx, {
            type: 'line',
            data: {
                labels: years,
                datasets: [{
                    label: 'Cumulative CO₂ Savings (tons)',
                    data: cumulativeCO2,
                    borderColor: 'rgba(46, 204, 113, 1)',
                    backgroundColor: 'rgba(46, 204, 113, 0.2)',
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'CO₂ Savings (tons)'
                        }
                    },
                    x: {
                        title: {
                            display: true,
                            text: 'Years'
                        }
                    }
                }
            }
        });
    }
    
    function updateGridChart(data) {
        const ctx = document.getElementById('gridChart').getContext('2d');
        if (charts.grid) charts.grid.destroy();
        
        charts.grid = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Self Consumption', 'Grid Dependency'],
                datasets: [{
                    data: [
                        data.grid_analysis.self_consumption_percent,
                        data.grid_analysis.grid_dependency_percent
                    ],
                    backgroundColor: [
                        'rgba(46, 204, 113, 0.8)',
                        'rgba(231, 76, 60, 0.8)'
                    ]
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
        
        document.getElementById('grid-details').innerHTML = 
            '<div class="info-card">' +
            '<h4>Grid Interaction Analysis</h4>' +
            '<p><strong>Self Consumption:</strong> ' + data.grid_analysis.self_consumption_percent + '%</p>' +
            '<p><strong>Daily Grid Import:</strong> ' + data.grid_analysis.daily_grid_import_kwh + ' kWh</p>' +
            '<p><strong>Daily Export Potential:</strong> ' + data.grid_analysis.daily_excess_export_kwh + ' kWh</p>' +
            '<p><strong>Grid Independence:</strong> ' + (data.grid_analysis.grid_dependency_percent < 25 ? 'High' : data.grid_analysis.grid_dependency_percent < 50 ? 'Medium' : 'Low') + '</p>' +
            '</div>';
    }
    
    function updateComparisonChart(data) {
        const ctx = document.getElementById('comparisonChart').getContext('2d');
        if (charts.comparison) charts.comparison.destroy();
        
        const systems = data.system_comparison;
        
        charts.comparison = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: systems.map(function(s) { return s.system_size_kw + 'kW System'; }),
                datasets: [{
                    label: 'Total Cost ($)',
                    data: systems.map(function(s) { return s.total_cost; }),
                    backgroundColor: 'rgba(102, 126, 234, 0.6)',
                    yAxisID: 'y'
                }, {
                    label: 'Payback Period (years)',
                    data: systems.map(function(s) { return s.payback_period; }),
                    backgroundColor: 'rgba(231, 76, 60, 0.6)',
                    yAxisID: 'y1'
                }]
            },
            options: {
                responsive: true,
                scales: {
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        title: {
                            display: true,
                            text: 'Cost ($)'
                        }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        title: {
                            display: true,
                            text: 'Years'
                        },
                        grid: {
                            drawOnChartArea: false
                        }
                    }
                }
            }
        });
        
        var comparisonDetailsHTML = '<div class="info-card"><h4>System Size Comparison</h4>';
        systems.forEach(function(s) {
            comparisonDetailsHTML += `<p><strong>${s.system_size_kw}kW:</strong> ${s.total_cost.toLocaleString()} - ${s.payback_period} years payback - ${s.yearly_production_kwh} kWh/year</p>`;
        });
        comparisonDetailsHTML += '</div>';
        
        document.getElementById('comparison-details').innerHTML = comparisonDetailsHTML;
    }
    
    function updateDegradationChart(data) {
        const ctx = document.getElementById('degradationChart').getContext('2d');
        if (charts.degradation) charts.degradation.destroy();
        
        const degradationData = data.degradation_forecast;
        
        charts.degradation = new Chart(ctx, {
            type: 'line',
            data: {
                labels: degradationData.map(function(d) { return 'Year ' + d.year; }),
                datasets: [{
                    label: 'Annual Production (kWh)',
                    data: degradationData.map(function(d) { return d.production_kwh; }),
                    borderColor: 'rgba(102, 126, 234, 1)',
                    backgroundColor: 'rgba(102, 126, 234, 0.2)',
                    fill: true,
                    tension: 0.4,
                    yAxisID: 'y'
                }, {
                    label: 'Efficiency (%)',
                    data: degradationData.map(function(d) { return d.efficiency_percent; }),
                    borderColor: 'rgba(231, 76, 60, 1)',
                    backgroundColor: 'rgba(231, 76, 60, 0.2)',
                    yAxisID: 'y1'
                }]
            },
            options: {
                responsive: true,
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Production (kWh)'
                        }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        max: 100,
                        title: {
                            display: true,
                            text: 'Efficiency (%)'
                        },
                        grid: {
                            drawOnChartArea: false
                        }
                    }
                }
            }
        });
    }
    
    function updateDetailedInfo(data) {
        document.getElementById('tilt-info').innerHTML = 
            '<div class="info-card">' +
            '<h4>Optimal Panel Positioning</h4>' +
            '<p><strong>Optimal Year-Round Tilt:</strong> ' + data.tilt_angles.optimal_angle + '°</p>' +
            '<p><strong>Winter Optimization:</strong> ' + data.tilt_angles.winter_angle + '°</p>' +
            '<p><strong>Summer Optimization:</strong> ' + data.tilt_angles.summer_angle + '°</p>' +
            '<p><strong>Recommendation:</strong> Use ' + data.tilt_angles.optimal_angle + '° for fixed installation or adjust seasonally for 5-10% better performance.</p>' +
            '</div>';
        
        var maintenanceHTML = '<div class="info-card"><h4>Maintenance Schedule</h4>';
        Object.keys(data.maintenance_schedule).forEach(function(key) {
            var value = data.maintenance_schedule[key];
            var displayKey = key.replace(/_/g, ' ').replace(/\b\w/g, function(l) { return l.toUpperCase(); });
            maintenanceHTML += '<div class="maintenance-item">';
            maintenanceHTML += '<span><strong>' + displayKey + ':</strong></span>';
            maintenanceHTML += '<span>' + value + '</span>';
            maintenanceHTML += '</div>';
        });
        maintenanceHTML += '</div>';
        maintenanceHTML += '<div class="info-card">';
        maintenanceHTML += '<h4>Maintenance Tips</h4>';
        maintenanceHTML += '<ul>';
        maintenanceHTML += '<li>Clean panels during early morning or late evening</li>';
        maintenanceHTML += '<li>Use soft brush and clean water only</li>';
        maintenanceHTML += '<li>Check for loose connections quarterly</li>';
        maintenanceHTML += '<li>Monitor system performance daily</li>';
        maintenanceHTML += '<li>Schedule professional inspection annually</li>';
        maintenanceHTML += '</ul>';
        maintenanceHTML += '</div>';
        
        document.getElementById('maintenance-info').innerHTML = maintenanceHTML;
    }
    
    function showTab(tabName, event) {
        document.querySelectorAll('.tab-content').forEach(function(content) {
            content.classList.remove('active');
        });
        
        document.querySelectorAll('.tab').forEach(function(tab) {
            tab.classList.remove('active');
        });
        
        // map tabName to id used in HTML
        const idMap = {
            'production': 'production-tab',
            'cost': 'cost-tab',
            'environmental': 'environmental-tab',
            'grid': 'grid-tab'
        };
        const tabId = idMap[tabName] || tabName + '-tab';
        const tabElement = document.getElementById(tabId);
        if (tabElement) tabElement.classList.add('active');
        if (event && event.target) event.target.classList.add('active');
    }
    
    function showDetailTab(tabName, event) {
        document.querySelectorAll('#tilt-detail, #comparison-detail, #maintenance-detail, #degradation-detail').forEach(function(content) {
            content.classList.remove('active');
        });
        
        // handle the detail tab buttons
        document.querySelectorAll('.chart-container:last-child .tab').forEach(function(tab) {
            tab.classList.remove('active');
        });
        
        const idMap = {
            'tilt': 'tilt-detail',
            'comparison': 'comparison-detail',
            'maintenance': 'maintenance-detail',
            'degradation': 'degradation-detail'
        };
        const detailId = idMap[tabName] || tabName + '-detail';
        const elem = document.getElementById(detailId);
        if (elem) elem.classList.add('active');
        if (event && event.target) event.target.classList.add('active');
    }
    
    window.addEventListener('load', function() {
        loadSampleData();
    });
</script>
</body>
</html>
    '''
    return html_content

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=7860, debug=True)