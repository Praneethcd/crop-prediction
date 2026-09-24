from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
import joblib
import numpy as np
import os
import json
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from models.prediction_models import PredictionModels
from database import (
    init_db, get_user_by_email, get_user_by_id, create_user,
    save_prediction, get_user_predictions, save_forum_post, get_forum_posts,
    get_user_forum_posts, save_marketplace_listing, get_marketplace_listings,
    get_user_listings, get_all_users, get_user_stats, delete_user,
    get_recent_predictions, delete_forum_post, delete_marketplace_listing
)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'

# Initialize database
init_db()

# Initialize prediction models
try:
    prediction_models = PredictionModels()
    models_loaded = True
except Exception as e:
    print(f"Error loading models: {e}")
    models_loaded = False


# --- Auth Decorators ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please login to access this page.', 'danger')
                return redirect(url_for('login'))
            if session.get('role') not in roles:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# --- Auth Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        user = get_user_by_email(email)
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['email'] = user['email']
            session['role'] = user['role']
            session['full_name'] = user['full_name']
            flash(f'Welcome back, {user["full_name"]}!', 'success')
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('dashboard'))
        flash('Invalid email or password.', 'danger')
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('user_id'):
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        location = request.form.get('location', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'user')

        if role not in ('farmer', 'user'):
            role = 'user'

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return render_template('register.html')

        password_hash = generate_password_hash(password)
        success = create_user(username, email, password_hash, role, full_name, phone, location)
        if success:
            flash('Account created successfully! Please login.', 'success')
            return redirect(url_for('login'))
        flash('Username or email already exists.', 'danger')
    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))


# --- Dashboard Routes ---
@app.route('/dashboard')
@login_required
def dashboard():
    role = session.get('role')
    if role == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif role == 'farmer':
        return redirect(url_for('farmer_dashboard_view'))
    return redirect(url_for('user_dashboard_view'))


@app.route('/admin')
@role_required('admin')
def admin_dashboard():
    stats = get_user_stats()
    users = get_all_users()
    recent_preds = get_recent_predictions(10)
    forum = get_forum_posts(20)
    listings = get_marketplace_listings(20)
    return render_template('admin_dashboard.html',
                           stats=stats, users=users,
                           recent_predictions=recent_preds,
                           forum_posts=forum,
                           marketplace_listings=listings)


@app.route('/admin/delete-user/<int:user_id>', methods=['POST'])
@role_required('admin')
def admin_delete_user(user_id):
    if user_id == session.get('user_id'):
        flash('Cannot delete your own account.', 'danger')
    else:
        delete_user(user_id)
        flash('User deleted successfully.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete-post/<int:post_id>', methods=['POST'])
@role_required('admin')
def admin_delete_post(post_id):
    delete_forum_post(post_id)
    flash('Post deleted.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete-listing/<int:listing_id>', methods=['POST'])
@role_required('admin')
def admin_delete_listing(listing_id):
    delete_marketplace_listing(listing_id)
    flash('Listing deleted.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/farmer-dashboard')
@role_required('farmer')
def farmer_dashboard_view():
    uid = session['user_id']
    predictions = get_user_predictions(uid)
    listings = get_user_listings(uid)
    forum_posts = get_user_forum_posts(uid)
    return render_template('farmer_dashboard.html',
                           predictions=predictions,
                           listings=listings,
                           forum_posts=forum_posts)


@app.route('/user-dashboard')
@role_required('user')
def user_dashboard_view():
    uid = session['user_id']
    predictions = get_user_predictions(uid)
    return render_template('user_dashboard.html', predictions=predictions)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/yield-prediction')
def yield_prediction():
    return render_template('yield_prediction.html')

@app.route('/disease-prediction')
def disease_prediction():
    return render_template('disease_prediction.html')

@app.route('/fertilizer-recommendation')
def fertilizer_recommendation():
    return render_template('fertilizer_recommendation.html')

@app.route('/weather-prediction')
def weather_prediction():
    return render_template('weather_prediction.html')

# API Routes for predictions
@app.route('/api/predict-yield', methods=['POST'])
def api_predict_yield():
    try:
        data = request.json
        rainfall = float(data['rainfall'])
        pesticide = float(data['pesticide'])
        temperature = float(data['temperature'])
        crop = data.get('crop', 'Maize')

        if models_loaded:
            yield_pred = prediction_models.predict_yield(rainfall, pesticide, temperature)
            message = f'Predicted yield for {crop}: {yield_pred} hg/ha'
        else:
            base_yield = 30000
            rain_factor = min(rainfall / 1000, 1.5)
            pest_factor = min(pesticide / 200, 1.2)
            temp_factor = max(0.5, 1 - abs(temperature - 25) / 25)
            yield_pred = round(base_yield * rain_factor * pest_factor * temp_factor)
            message = f'Estimated yield for {crop}: {yield_pred} hg/ha'

        if session.get('user_id'):
            save_prediction(
                session['user_id'], 'Yield Prediction',
                json.dumps({'rainfall': rainfall, 'pesticide': pesticide, 'temperature': temperature, 'crop': crop}),
                message
            )

        return jsonify({
            'success': True, 'prediction': yield_pred,
            'crop': crop, 'message': message
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/predict-disease', methods=['POST'])
def api_predict_disease():
    try:
        data = request.json
        rainfall = float(data['rainfall'])
        temperature = float(data['temperature'])
        humidity = float(data.get('humidity', 70))
        pesticide = float(data.get('pesticide', 100))
        
        if models_loaded:
            disease_risk = prediction_models.predict_disease_risk(rainfall, temperature, pesticide)
        else:
            # Fallback logic
            risk_score = 0
            if rainfall > 1000: risk_score += 2
            elif rainfall > 500: risk_score += 1
            if 15 <= temperature <= 25: risk_score += 2
            if humidity > 80: risk_score += 1
            if pesticide < 100: risk_score += 1
            
            if risk_score >= 4: disease_risk = 'High'
            elif risk_score >= 2: disease_risk = 'Medium'
            else: disease_risk = 'Low'
        
        recommendations = {
            'High': 'Apply fungicide, improve drainage, reduce plant density',
            'Medium': 'Monitor crops closely, ensure proper ventilation',
            'Low': 'Continue regular monitoring, maintain good practices'
        }
        
        message = f'Disease risk level: {disease_risk}'
        if session.get('user_id'):
            save_prediction(
                session['user_id'], 'Disease Prediction',
                json.dumps({'rainfall': rainfall, 'temperature': temperature, 'humidity': humidity}),
                message
            )

        return jsonify({
            'success': True,
            'risk_level': disease_risk,
            'recommendation': recommendations.get(disease_risk, 'Monitor regularly'),
            'message': message
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# @app.route('/api/recommend-fertilizer', methods=['POST'])
# def api_recommend_fertilizer():
#     try:
#         data = request.json
#         crop = data['crop']
#         rainfall = float(data['rainfall'])
#         soil_type = data.get('soil_type', 'medium')
        
#         if models_loaded:
#             recommendation = prediction_models.recommend_fertilizer(crop, rainfall)
#         else:
#             # Fallback fertilizer recommendations
#             fertilizer_base = {
#                 'Maize': {'N': 120, 'P': 60, 'K': 40},
#                 'Rice': {'N': 100, 'P': 50, 'K': 50},
#                 'Potatoes': {'N': 150, 'P': 80, 'K': 120},
#                 'Soybeans': {'N': 20, 'P': 40, 'K': 60}
#             }
            
#             crop_key = crop.replace(',', '').replace(' paddy', '').strip()
#             base = fertilizer_base.get(crop_key, fertilizer_base['Maize'])
            
#             # Adjust for rainfall
#             rain_factor = 1.2 if rainfall < 500 else 0.9 if rainfall > 1200 else 1.0
            
#             recommendation = {
#                 'matched_crop': crop_key,
#                 'nitrogen_kg_ha': round(base['N'] * rain_factor),
#                 'phosphorus_kg_ha': round(base['P'] * rain_factor),
#                 'potassium_kg_ha': round(base['K'] * rain_factor),
#                 'recommendation': f"Apply {round(base['N'] * rain_factor)}kg/ha N, {round(base['P'] * rain_factor)}kg/ha P, {round(base['K'] * rain_factor)}kg/ha K"
#             }
        
#         return jsonify({
#             'success': True,
#             'fertilizer': recommendation,
#             'message': 'Fertilizer recommendation generated successfully'
#         })
#     except Exception as e:
#         return jsonify({'success': False, 'error': str(e)})



@app.route('/api/recommend-fertilizer', methods=['POST'])
def api_recommend_fertilizer():
    try:
        data = request.json
        crop = data['crop']
        rainfall = float(data['rainfall'])
        soil_type = data.get('soil_type', 'medium')
        field_size = float(data.get('field_size', 1.0))
        growth_stage = data.get('growth_stage', 'vegetative')
        
        if models_loaded:
            try:
                recommendation = prediction_models.recommend_fertilizer(crop, rainfall)
                if recommendation:
                    if session.get('user_id'):
                        save_prediction(
                            session['user_id'], 'Fertilizer Recommendation',
                            json.dumps({'crop': crop, 'rainfall': rainfall, 'soil_type': soil_type}),
                            f"Fertilizer recommendation for {crop}"
                        )
                    return jsonify({
                        'success': True,
                        'fertilizer': recommendation,
                        'field_size': field_size,
                        'message': 'Fertilizer recommendation generated successfully'
                    })
            except Exception as model_error:
                print(f"Model error: {model_error}")

        # Enhanced fallback fertilizer recommendations with random variations
        recommendation = generate_fallback_fertilizer_recommendation(
            crop, rainfall, soil_type, growth_stage, field_size
        )

        if session.get('user_id'):
            save_prediction(
                session['user_id'], 'Fertilizer Recommendation',
                json.dumps({'crop': crop, 'rainfall': rainfall, 'soil_type': soil_type}),
                recommendation.get('recommendation', f"Fertilizer recommendation for {crop}")
            )

        return jsonify({
            'success': True,
            'fertilizer': recommendation,
            'field_size': field_size,
            'message': 'Fertilizer recommendation generated successfully (estimated values)',
            'note': 'Recommendations based on general agricultural guidelines'
        })

    except Exception as e:
        print(f"Fertilizer recommendation error: {e}")
        return jsonify({'success': False, 'error': f'Unable to generate recommendation: {str(e)}'})

def generate_fallback_fertilizer_recommendation(crop, rainfall, soil_type, growth_stage, field_size):
    """
    Generate realistic fertilizer recommendations with random variations
    """
    import random
    
    # Base NPK values for different crops (kg/ha)
    crop_npk_base = {
        'Maize': {'N': 120, 'P': 60, 'K': 40},
        'Rice': {'N': 100, 'P': 50, 'K': 50},
        'Potatoes': {'N': 150, 'P': 80, 'K': 120},
        'Soybeans': {'N': 20, 'P': 40, 'K': 60},  # Lower N due to nitrogen fixation
        'Wheat': {'N': 120, 'P': 40, 'K': 30},
        'Sorghum': {'N': 80, 'P': 40, 'K': 40},
        'Cotton': {'N': 120, 'P': 60, 'K': 60},
        'Sugarcane': {'N': 200, 'P': 80, 'K': 100},
        'Tomatoes': {'N': 150, 'P': 100, 'K': 150},
    }
    
    # Find matching crop (case-insensitive, partial matching)
    matched_crop = 'Maize'  # Default
    crop_clean = crop.replace(',', '').replace(' paddy', '').replace('(', '').replace(')', '').strip()
    
    for crop_key in crop_npk_base.keys():
        if crop_key.lower() in crop_clean.lower() or crop_clean.lower() in crop_key.lower():
            matched_crop = crop_key
            break
    
    base_npk = crop_npk_base[matched_crop]
    
    # Rainfall adjustments
    if rainfall < 400:  # Low rainfall
        rain_factor_n = random.uniform(1.15, 1.25)
        rain_factor_p = random.uniform(1.10, 1.20)
        rain_factor_k = random.uniform(1.05, 1.15)
        rainfall_note = "Low rainfall: Increased fertilizer needs"
    elif rainfall > 1500:  # High rainfall
        rain_factor_n = random.uniform(0.75, 0.85)
        rain_factor_p = random.uniform(0.80, 0.90)
        rain_factor_k = random.uniform(1.10, 1.20)
        rainfall_note = "High rainfall: Reduced N&P, increased K for leaching prevention"
    else:  # Normal rainfall
        rain_factor_n = random.uniform(0.95, 1.05)
        rain_factor_p = random.uniform(0.95, 1.05)
        rain_factor_k = random.uniform(0.95, 1.05)
        rainfall_note = "Normal rainfall: Standard fertilizer application"
    
    # Soil type adjustments
    soil_adjustments = {
        'clay': {'N': 0.9, 'P': 1.1, 'K': 0.9},
        'sandy': {'N': 1.1, 'P': 1.2, 'K': 1.1},
        'loamy': {'N': 1.0, 'P': 1.0, 'K': 1.0},
        'silt': {'N': 0.95, 'P': 1.05, 'K': 0.95},
        'red': {'N': 1.05, 'P': 1.15, 'K': 1.0},
        'black': {'N': 0.95, 'P': 0.9, 'K': 1.05}
    }
    
    soil_factor = soil_adjustments.get(soil_type, {'N': 1.0, 'P': 1.0, 'K': 1.0})
    
    # Growth stage adjustments
    stage_adjustments = {
        'pre-sowing': {'N': 0.3, 'P': 0.5, 'K': 0.3},
        'sowing': {'N': 0.4, 'P': 0.6, 'K': 0.4},
        'vegetative': {'N': 1.2, 'P': 0.8, 'K': 0.9},
        'flowering': {'N': 0.6, 'P': 1.2, 'K': 1.1},
        'maturity': {'N': 0.2, 'P': 0.3, 'K': 0.8}
    }
    
    stage_factor = stage_adjustments.get(growth_stage, {'N': 1.0, 'P': 1.0, 'K': 1.0})
    
    # Calculate final NPK values with random variation (±10%)
    final_n = round(base_npk['N'] * rain_factor_n * soil_factor['N'] * stage_factor['N'] * random.uniform(0.9, 1.1))
    final_p = round(base_npk['P'] * rain_factor_p * soil_factor['P'] * stage_factor['P'] * random.uniform(0.9, 1.1))
    final_k = round(base_npk['K'] * rain_factor_k * soil_factor['K'] * stage_factor['K'] * random.uniform(0.9, 1.1))
    
    # Ensure minimum values
    final_n = max(final_n, 10)
    final_p = max(final_p, 5)
    final_k = max(final_k, 5)
    
    # Calculate total amounts for field
    total_n = round(final_n * field_size, 1)
    total_p = round(final_p * field_size, 1)
    total_k = round(final_k * field_size, 1)
    
    # Generate application schedule
    application_schedule = generate_application_schedule(growth_stage, final_n, final_p, final_k)
    
    # Generate fertilizer types
    fertilizer_types = generate_fertilizer_types(final_n, final_p, final_k)
    
    return {
        'matched_crop': matched_crop,
        'nitrogen_kg_ha': final_n,
        'phosphorus_kg_ha': final_p,
        'potassium_kg_ha': final_k,
        'total_nitrogen_kg': total_n,
        'total_phosphorus_kg': total_p,
        'total_potassium_kg': total_k,
        'recommendation': f"Apply {final_n}kg/ha N, {final_p}kg/ha P, {final_k}kg/ha K for {matched_crop}",
        'rainfall_factor': rainfall_note,
        'soil_type': soil_type.title(),
        'growth_stage': growth_stage.replace('_', ' ').title(),
        'application_schedule': application_schedule,
        'fertilizer_types': fertilizer_types,
        'cost_estimate': calculate_fertilizer_cost(final_n, final_p, final_k, field_size)
    }

def generate_application_schedule(growth_stage, n, p, k):
    """Generate application schedule based on growth stage"""
    import random
    
    schedules = {
        'pre-sowing': {
            'basal': {'N': 100, 'P': 100, 'K': 100},
            'schedule': "Apply all fertilizers as basal dose before sowing"
        },
        'sowing': {
            'basal': {'N': 50, 'P': 100, 'K': 50},
            'top_dress_1': {'N': 50, 'P': 0, 'K': 50},
            'schedule': "50% N&K as basal, 50% N&K after 3-4 weeks. All P as basal."
        },
        'vegetative': {
            'basal': {'N': 40, 'P': 100, 'K': 40},
            'top_dress_1': {'N': 40, 'P': 0, 'K': 40},
            'top_dress_2': {'N': 20, 'P': 0, 'K': 20},
            'schedule': "40% N&K basal, 40% at 25 days, 20% at 45 days. All P basal."
        },
        'flowering': {
            'current': {'N': 30, 'P': 70, 'K': 60},
            'next': {'N': 20, 'P': 30, 'K': 40},
            'schedule': "Focus on P&K for flower/fruit development. Reduce N."
        },
        'maturity': {
            'current': {'N': 10, 'P': 20, 'K': 50},
            'schedule': "Minimal fertilizer. Focus on K for fruit filling."
        }
    }
    
    return schedules.get(growth_stage, schedules['vegetative'])

def generate_fertilizer_types(n, p, k):
    """Suggest specific fertilizer types"""
    import random
    
    fertilizer_options = []
    
    # Nitrogen sources
    n_sources = ['Urea (46% N)', 'Ammonium Sulphate (21% N)', 'CAN (26% N)', 'DAP (18% N)']
    fertilizer_options.append({
        'nutrient': 'Nitrogen',
        'recommended_source': random.choice(n_sources),
        'quantity_needed': f"{round(n/0.46 if 'Urea' in n_sources[0] else n/0.21, 1)} kg/ha"
    })
    
    # Phosphorus sources
    p_sources = ['DAP (46% P2O5)', 'SSP (16% P2O5)', 'TSP (46% P2O5)', 'Bone Meal (22% P2O5)']
    fertilizer_options.append({
        'nutrient': 'Phosphorus',
        'recommended_source': random.choice(p_sources),
        'quantity_needed': f"{round(p/0.46 if 'DAP' in p_sources[0] else p/0.16, 1)} kg/ha"
    })
    
    # Potassium sources
    k_sources = ['MOP (60% K2O)', 'SOP (50% K2O)', 'Potash (50% K2O)', 'Ash (5% K2O)']
    fertilizer_options.append({
        'nutrient': 'Potassium',
        'recommended_source': random.choice(k_sources),
        'quantity_needed': f"{round(k/0.60 if 'MOP' in k_sources[0] else k/0.50, 1)} kg/ha"
    })
    
    return fertilizer_options

def calculate_fertilizer_cost(n, p, k, field_size):
    """Calculate estimated fertilizer cost"""
    import random
    
    # Approximate costs per kg of nutrient (in INR)
    n_cost = random.uniform(25, 35)  # per kg N
    p_cost = random.uniform(50, 70)  # per kg P
    k_cost = random.uniform(30, 45)  # per kg K
    
    total_cost = (n * n_cost + p * p_cost + k * k_cost) * field_size
    
    return {
        'per_hectare': round(n * n_cost + p * p_cost + k * k_cost, 2),
        'total_field': round(total_cost, 2),
        'currency': 'INR',
        'breakdown': {
            'nitrogen_cost': round(n * n_cost * field_size, 2),
            'phosphorus_cost': round(p * p_cost * field_size, 2),
            'potassium_cost': round(k * k_cost * field_size, 2)
        }
    }




@app.route('/api/predict-weather', methods=['POST'])
def api_predict_weather():
    try:
        data = request.json
        year = int(data.get('year', 2025))
        location = data.get('location', 'General')
        
        if models_loaded:
            rainfall_pred = prediction_models.predict_weather(year)
        else:
            # Simple trend calculation
            base_rainfall = 800
            year_factor = (year - 2020) * 5  # 5mm change per year
            rainfall_pred = round(base_rainfall + year_factor + np.random.randint(-50, 50))
        
        # Weather recommendations based on prediction
        if rainfall_pred < 400:
            weather_advice = "Low rainfall expected. Consider drought-resistant crops and irrigation planning."
        elif rainfall_pred > 1500:
            weather_advice = "High rainfall expected. Ensure proper drainage and flood management."
        else:
            weather_advice = "Normal rainfall expected. Good conditions for most crops."
        
        message = f'Weather prediction for {year}: {rainfall_pred}mm rainfall'
        if session.get('user_id'):
            save_prediction(
                session['user_id'], 'Weather Prediction',
                json.dumps({'year': year, 'location': location}),
                message
            )

        return jsonify({
            'success': True,
            'year': year,
            'location': location,
            'predicted_rainfall': rainfall_pred,
            'advice': weather_advice,
            'message': message
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/crop-recommendation')
def crop_recommendation():
    return render_template('crop_recommendation.html')

@app.route('/api/recommend-crop', methods=['POST'])
def api_recommend_crop():
    try:
        data = request.json
        rainfall = float(data['rainfall'])
        temperature = float(data['temperature'])
        humidity = float(data['humidity'])
        soil_type = data['soil_type']
        ph_level = float(data.get('ph_level', 7.0))
        season = data.get('season', 'kharif')
        farm_size = float(data.get('farm_size', 1.0))
        water_availability = data.get('water_availability', 'moderate')
        experience_level = data.get('experience_level', 'intermediate')
        market_preference = data.get('market_preference', 'food_grain')
        
        # Generate crop recommendations
        recommendations = generate_crop_recommendations(
            rainfall, temperature, humidity, soil_type, ph_level, 
            season, farm_size, water_availability, experience_level, market_preference
        )
        
        top_crop = recommendations[0]['crop_name'] if recommendations else 'N/A'
        if session.get('user_id'):
            save_prediction(
                session['user_id'], 'Crop Recommendation',
                json.dumps({'rainfall': rainfall, 'temperature': temperature, 'soil_type': soil_type, 'season': season}),
                f'Top recommendation: {top_crop}'
            )

        return jsonify({
            'success': True,
            'recommendations': recommendations,
            'message': 'Crop recommendations generated successfully',
            'parameters_used': {
                'rainfall': rainfall,
                'temperature': temperature,
                'humidity': humidity,
                'soil_type': soil_type,
                'season': season
            }
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

def generate_crop_recommendations(rainfall, temperature, humidity, soil_type, ph_level, season, farm_size, water_availability, experience_level, market_preference):
    """
    Generate crop recommendations based on multiple parameters
    """
    import random
    
    # Comprehensive crop database with requirements
    crop_database = {
        'Rice': {
            'rainfall': (1000, 2500),
            'temperature': (20, 35),
            'humidity': (70, 95),
            'soil_types': ['clay', 'loamy', 'alluvial'],
            'ph_range': (5.5, 7.0),
            'water_need': 'high',
            'season': ['kharif', 'rabi'],
            'experience': ['beginner', 'intermediate', 'advanced'],
            'market_type': 'food_grain',
            'yield_potential': 'high',
            'investment': 'medium',
            'duration': '120-150 days',
            'profit_margin': 'medium'
        },
        'Wheat': {
            'rainfall': (300, 1000),
            'temperature': (15, 25),
            'humidity': (50, 70),
            'soil_types': ['loamy', 'clay', 'black'],
            'ph_range': (6.0, 7.5),
            'water_need': 'medium',
            'season': ['rabi'],
            'experience': ['beginner', 'intermediate', 'advanced'],
            'market_type': 'food_grain',
            'yield_potential': 'high',
            'investment': 'medium',
            'duration': '120-140 days',
            'profit_margin': 'medium'
        },
        'Maize': {
            'rainfall': (500, 1200),
            'temperature': (18, 32),
            'humidity': (60, 80),
            'soil_types': ['loamy', 'sandy', 'red'],
            'ph_range': (5.5, 7.0),
            'water_need': 'medium',
            'season': ['kharif', 'rabi', 'zaid'],
            'experience': ['beginner', 'intermediate', 'advanced'],
            'market_type': 'food_grain',
            'yield_potential': 'high',
            'investment': 'medium',
            'duration': '90-120 days',
            'profit_margin': 'high'
        },
        'Cotton': {
            'rainfall': (500, 1200),
            'temperature': (21, 35),
            'humidity': (60, 85),
            'soil_types': ['black', 'alluvial', 'red'],
            'ph_range': (6.0, 8.0),
            'water_need': 'medium',
            'season': ['kharif'],
            'experience': ['intermediate', 'advanced'],
            'market_type': 'cash_crop',
            'yield_potential': 'high',
            'investment': 'high',
            'duration': '180-200 days',
            'profit_margin': 'very_high'
        },
        'Sugarcane': {
            'rainfall': (1000, 2000),
            'temperature': (20, 35),
            'humidity': (70, 90),
            'soil_types': ['loamy', 'clay', 'alluvial'],
            'ph_range': (6.0, 7.5),
            'water_need': 'very_high',
            'season': ['annual'],
            'experience': ['intermediate', 'advanced'],
            'market_type': 'cash_crop',
            'yield_potential': 'very_high',
            'investment': 'very_high',
            'duration': '12-18 months',
            'profit_margin': 'high'
        },
        'Soybeans': {
            'rainfall': (400, 800),
            'temperature': (20, 30),
            'humidity': (60, 80),
            'soil_types': ['loamy', 'black', 'red'],
            'ph_range': (6.0, 7.5),
            'water_need': 'medium',
            'season': ['kharif'],
            'experience': ['beginner', 'intermediate'],
            'market_type': 'oilseed',
            'yield_potential': 'medium',
            'investment': 'low',
            'duration': '90-110 days',
            'profit_margin': 'medium'
        },
        'Groundnut': {
            'rainfall': (500, 1000),
            'temperature': (20, 30),
            'humidity': (65, 85),
            'soil_types': ['sandy', 'red', 'black'],
            'ph_range': (6.0, 7.0),
            'water_need': 'medium',
            'season': ['kharif', 'rabi'],
            'experience': ['beginner', 'intermediate'],
            'market_type': 'oilseed',
            'yield_potential': 'medium',
            'investment': 'medium',
            'duration': '100-120 days',
            'profit_margin': 'medium'
        },
        'Tomato': {
            'rainfall': (400, 800),
            'temperature': (18, 27),
            'humidity': (60, 80),
            'soil_types': ['loamy', 'sandy', 'red'],
            'ph_range': (6.0, 7.0),
            'water_need': 'high',
            'season': ['rabi', 'zaid'],
            'experience': ['intermediate', 'advanced'],
            'market_type': 'vegetable',
            'yield_potential': 'high',
            'investment': 'high',
            'duration': '90-120 days',
            'profit_margin': 'very_high'
        },
        'Potato': {
            'rainfall': (400, 700),
            'temperature': (15, 25),
            'humidity': (60, 80),
            'soil_types': ['loamy', 'sandy', 'red'],
            'ph_range': (5.5, 6.5),
            'water_need': 'medium',
            'season': ['rabi'],
            'experience': ['intermediate', 'advanced'],
            'market_type': 'vegetable',
            'yield_potential': 'high',
            'investment': 'high',
            'duration': '90-120 days',
            'profit_margin': 'high'
        },
        'Onion': {
            'rainfall': (300, 600),
            'temperature': (15, 25),
            'humidity': (60, 70),
            'soil_types': ['loamy', 'sandy', 'alluvial'],
            'ph_range': (6.0, 7.5),
            'water_need': 'medium',
            'season': ['rabi', 'kharif'],
            'experience': ['intermediate', 'advanced'],
            'market_type': 'vegetable',
            'yield_potential': 'medium',
            'investment': 'medium',
            'duration': '120-150 days',
            'profit_margin': 'high'
        },
        'Sunflower': {
            'rainfall': (400, 800),
            'temperature': (20, 30),
            'humidity': (60, 80),
            'soil_types': ['loamy', 'sandy', 'red'],
            'ph_range': (6.0, 7.5),
            'water_need': 'medium',
            'season': ['kharif', 'rabi'],
            'experience': ['beginner', 'intermediate'],
            'market_type': 'oilseed',
            'yield_potential': 'medium',
            'investment': 'low',
            'duration': '90-110 days',
            'profit_margin': 'medium'
        },
        'Chili': {
            'rainfall': (600, 1200),
            'temperature': (20, 30),
            'humidity': (70, 85),
            'soil_types': ['loamy', 'sandy', 'red'],
            'ph_range': (6.0, 7.0),
            'water_need': 'medium',
            'season': ['kharif', 'rabi'],
            'experience': ['intermediate', 'advanced'],
            'market_type': 'spice',
            'yield_potential': 'high',
            'investment': 'medium',
            'duration': '150-180 days',
            'profit_margin': 'very_high'
        }
    }
    
    # Score each crop based on suitability
    crop_scores = {}
    
    for crop, requirements in crop_database.items():
        score = 0
        max_score = 100
        details = []
        
        # Rainfall suitability (20 points)
        rain_min, rain_max = requirements['rainfall']
        if rain_min <= rainfall <= rain_max:
            rain_score = 20
            details.append(f"✓ Rainfall requirement met ({rain_min}-{rain_max}mm)")
        elif rainfall < rain_min:
            rain_score = max(0, 20 - (rain_min - rainfall) / rain_min * 20)
            details.append(f"⚠ Rainfall slightly low (needs {rain_min}-{rain_max}mm)")
        else:
            rain_score = max(0, 20 - (rainfall - rain_max) / rain_max * 20)
            details.append(f"⚠ Rainfall slightly high (optimal: {rain_min}-{rain_max}mm)")
        score += rain_score
        
        # Temperature suitability (20 points)
        temp_min, temp_max = requirements['temperature']
        if temp_min <= temperature <= temp_max:
            temp_score = 20
            details.append(f"✓ Temperature requirement met ({temp_min}-{temp_max}°C)")
        elif temperature < temp_min:
            temp_score = max(0, 20 - (temp_min - temperature) / temp_min * 20)
            details.append(f"⚠ Temperature slightly low (needs {temp_min}-{temp_max}°C)")
        else:
            temp_score = max(0, 20 - (temperature - temp_max) / temp_max * 20)
            details.append(f"⚠ Temperature slightly high (optimal: {temp_min}-{temp_max}°C)")
        score += temp_score
        
        # Soil type suitability (15 points)
        if soil_type in requirements['soil_types']:
            soil_score = 15
            details.append(f"✓ Suitable for {soil_type} soil")
        else:
            soil_score = 8
            details.append(f"⚠ Moderately suitable for {soil_type} soil")
        score += soil_score
        
        # pH suitability (10 points)
        ph_min, ph_max = requirements['ph_range']
        if ph_min <= ph_level <= ph_max:
            ph_score = 10
            details.append(f"✓ pH requirement met ({ph_min}-{ph_max})")
        else:
            ph_score = max(0, 10 - abs(ph_level - (ph_min + ph_max) / 2))
            details.append(f"⚠ pH adjustment may be needed (optimal: {ph_min}-{ph_max})")
        score += ph_score
        
        # Season suitability (10 points)
        if season in requirements['season'] or 'annual' in requirements['season']:
            season_score = 10
            details.append(f"✓ Suitable for {season} season")
        else:
            season_score = 5
            details.append(f"⚠ Not ideal season (best: {', '.join(requirements['season'])})")
        score += season_score
        
        # Experience level (10 points)
        if experience_level in requirements['experience']:
            exp_score = 10
            details.append(f"✓ Suitable for {experience_level} farmers")
        else:
            exp_score = 6
            details.append(f"⚠ May require {requirements['experience'][-1]} level expertise")
        score += exp_score
        
        # Water availability (10 points)
        water_compatibility = {
            'low': ['low', 'medium'],
            'medium': ['low', 'medium', 'high'],
            'high': ['medium', 'high', 'very_high'],
            'very_high': ['high', 'very_high']
        }
        
        if requirements['water_need'] in water_compatibility.get(water_availability, []):
            water_score = 10
            details.append(f"✓ Water requirement compatible")
        else:
            water_score = 5
            details.append(f"⚠ Water requirement: {requirements['water_need']}")
        score += water_score
        
        # Market preference (5 points)
        if requirements['market_type'] == market_preference or market_preference == 'mixed':
            market_score = 5
            details.append(f"✓ Matches market preference")
        else:
            market_score = 3
            details.append(f"⚠ Different market category: {requirements['market_type']}")
        score += market_score
        
        # Calculate percentage
        score_percentage = round((score / max_score) * 100, 1)
        
        # Determine recommendation level
        if score_percentage >= 80:
            recommendation_level = "Highly Recommended"
            level_class = "success"
        elif score_percentage >= 65:
            recommendation_level = "Recommended"
            level_class = "primary"
        elif score_percentage >= 50:
            recommendation_level = "Moderately Suitable"
            level_class = "warning"
        else:
            recommendation_level = "Not Recommended"
            level_class = "danger"
        
        crop_scores[crop] = {
            'score': score_percentage,
            'recommendation_level': recommendation_level,
            'level_class': level_class,
            'details': details,
            'requirements': requirements,
            'estimated_yield': calculate_estimated_yield(crop, score_percentage, farm_size),
            'investment_needed': calculate_investment(crop, farm_size),
            'profit_potential': requirements['profit_margin'],
            'duration': requirements['duration'],
            'special_notes': generate_special_notes(crop, rainfall, temperature, soil_type)
        }
    
    # Sort crops by score
    sorted_crops = sorted(crop_scores.items(), key=lambda x: x[1]['score'], reverse=True)
    
    # Return top recommendations
    return [
        {
            'crop_name': crop,
            'suitability_score': data['score'],
            'recommendation_level': data['recommendation_level'],
            'level_class': data['level_class'],
            'details': data['details'],
            'estimated_yield': data['estimated_yield'],
            'investment_needed': data['investment_needed'],
            'profit_potential': data['profit_potential'],
            'duration': data['duration'],
            'special_notes': data['special_notes'],
            'market_type': data['requirements']['market_type'].replace('_', ' ').title(),
            'water_requirement': data['requirements']['water_need'].title()
        }
        for crop, data in sorted_crops[:8]  # Top 8 recommendations
    ]

def calculate_estimated_yield(crop, score_percentage, farm_size):
    """Calculate estimated yield based on suitability score"""
    import random
    
    base_yields = {
        'Rice': 4000, 'Wheat': 3500, 'Maize': 5000, 'Cotton': 2000,
        'Sugarcane': 80000, 'Soybeans': 2500, 'Groundnut': 2000,
        'Tomato': 40000, 'Potato': 25000, 'Onion': 30000,
        'Sunflower': 1800, 'Chili': 3000
    }
    
    base_yield = base_yields.get(crop, 3000)
    yield_factor = score_percentage / 100
    estimated_yield_per_ha = round(base_yield * yield_factor * random.uniform(0.9, 1.1))
    total_yield = round(estimated_yield_per_ha * farm_size, 1)
    
    return {
        'per_hectare': estimated_yield_per_ha,
        'total_farm': total_yield,
        'unit': 'kg' if crop != 'Sugarcane' else 'tons'
    }

def calculate_investment(crop, farm_size):
    """Calculate investment requirements"""
    import random
    
    investment_per_ha = {
        'Rice': random.randint(25000, 35000),
        'Wheat': random.randint(20000, 30000),
        'Maize': random.randint(15000, 25000),
        'Cotton': random.randint(30000, 45000),
        'Sugarcane': random.randint(80000, 120000),
        'Soybeans': random.randint(12000, 18000),
        'Groundnut': random.randint(18000, 25000),
        'Tomato': random.randint(40000, 60000),
        'Potato': random.randint(35000, 50000),
        'Onion': random.randint(25000, 35000),
        'Sunflower': random.randint(10000, 15000),
        'Chili': random.randint(20000, 30000)
    }
    
    per_ha = investment_per_ha.get(crop, 20000)
    total = round(per_ha * farm_size)
    
    return {
        'per_hectare': per_ha,
        'total_farm': total,
        'currency': 'INR'
    }

def generate_special_notes(crop, rainfall, temperature, soil_type):
    """Generate special notes and tips for each crop"""
    notes = []
    
    crop_tips = {
        'Rice': ["Ensure proper water management", "Consider SRI method for better yields"],
        'Wheat': ["Apply nitrogen in split doses", "Monitor for rust diseases"],
        'Maize': ["Maintain proper plant spacing", "Good for intercropping"],
        'Cotton': ["Monitor for bollworm attacks", "Requires skilled labor"],
        'Sugarcane': ["Long-term crop commitment", "High water requirement"],
        'Soybeans': ["Natural nitrogen fixation", "Good rotation crop"],
        'Tomato': ["Requires staking and pruning", "High market demand"],
        'Potato': ["Cool storage needed", "Good processing potential"],
        'Onion': ["Long shelf life", "Export potential"],
        'Chili': ["High value spice crop", "Processing opportunities"]
    }
    
    if crop in crop_tips:
        notes.extend(crop_tips[crop])
    
    # Add weather-specific notes
    if rainfall > 1500:
        notes.append("High rainfall - ensure good drainage")
    elif rainfall < 400:
        notes.append("Low rainfall - plan irrigation carefully")
    
    if temperature > 35:
        notes.append("High temperature - consider shade nets")
    elif temperature < 15:
        notes.append("Low temperature - may need protection")
    
    return notes



@app.route('/farmer-connect')
def farmer_connect():
    return render_template('farmer_connect.html')

@app.route('/farmer-connect/forum')
def farmer_forum():
    return render_template('farmer_forum.html')

@app.route('/farmer-connect/experts')
def expert_advice():
    return render_template('expert_advice.html')

@app.route('/farmer-connect/marketplace')
def farmer_marketplace():
    return render_template('farmer_marketplace.html')

@app.route('/api/post-question', methods=['POST'])
def api_post_question():
    try:
        data = request.json
        question_data = {
            'id': generate_question_id(),
            'farmer_name': data['farmer_name'],
            'location': data['location'],
            'crop_type': data.get('crop_type', 'General'),
            'category': data['category'],
            'question': data['question'],
            'timestamp': get_current_timestamp(),
            'responses': [],
            'helpful_count': 0,
            'status': 'open'
        }
        
        # Save to database if logged in
        if session.get('user_id'):
            save_forum_post(
                session['user_id'],
                data.get('question', '')[:100],
                data['question'],
                data.get('category', 'General'),
                data.get('crop_type', 'General')
            )

        return jsonify({
            'success': True,
            'question_id': question_data['id'],
            'message': 'Your question has been posted successfully!',
            'estimated_response_time': '2-4 hours'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get-forum-posts')
def api_get_forum_posts():
    # Get real posts from DB
    db_posts = get_forum_posts(50)
    real_posts = []
    for p in db_posts:
        real_posts.append({
            'id': f'DB{p["id"]}',
            'farmer_name': p['full_name'],
            'location': p['location'] or 'Unknown',
            'crop_type': p['crop_type'],
            'category': p['category'],
            'question': p['content'],
            'timestamp': p['created_at'],
            'responses': 0,
            'helpful_count': 0,
            'status': 'open'
        })

    # Also include mock data for demo
    mock_posts = generate_mock_forum_posts()
    all_posts = real_posts + mock_posts

    return jsonify({
        'success': True,
        'posts': all_posts,
        'total_posts': len(all_posts)
    })

@app.route('/api/connect-farmers', methods=['POST'])
def api_connect_farmers():
    try:
        data = request.json
        location = data['location']
        crop_interest = data.get('crop_interest', 'All')
        
        # Mock farmer connections - in real app, query database
        nearby_farmers = generate_nearby_farmers(location, crop_interest)
        
        return jsonify({
            'success': True,
            'farmers': nearby_farmers,
            'message': f'Found {len(nearby_farmers)} farmers in your area'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/submit-listing', methods=['POST'])
def api_submit_listing():
    try:
        data = request.json
        listing = {
            'id': generate_listing_id(),
            'farmer_name': data['farmer_name'],
            'contact': data['contact'],
            'location': data['location'],
            'listing_type': data['listing_type'],
            'item_name': data['item_name'],
            'quantity': data['quantity'],
            'price': data.get('price', 'Negotiable'),
            'description': data['description'],
            'timestamp': get_current_timestamp(),
            'status': 'active'
        }

        # Save to database if logged in
        if session.get('user_id'):
            save_marketplace_listing(
                session['user_id'],
                data['item_name'],
                data['quantity'],
                data.get('price', 'Negotiable'),
                data.get('description', ''),
                data.get('listing_type', 'sell'),
                data.get('location', '')
            )

        return jsonify({
            'success': True,
            'listing_id': listing['id'],
            'message': 'Your listing has been posted successfully!'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Helper functions for Farmer Connect
def generate_question_id():
    import random, string
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def generate_listing_id():
    import random, string
    return 'LST' + ''.join(random.choices(string.digits, k=6))

def get_current_timestamp():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def generate_mock_forum_posts():
    import random
    from datetime import datetime, timedelta
    
    posts = [
        {
            'id': 'Q001',
            'farmer_name': 'Rajesh Kumar',
            'location': 'Punjab',
            'crop_type': 'Wheat',
            'category': 'Disease Management',
            'question': 'My wheat crop is showing yellow rust symptoms. What immediate action should I take?',
            'timestamp': (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
            'responses': 3,
            'helpful_count': 12,
            'status': 'answered'
        },
        {
            'id': 'Q002',
            'farmer_name': 'Priya Sharma',
            'location': 'Maharashtra',
            'crop_type': 'Cotton',
            'category': 'Pest Control',
            'question': 'How to control bollworm attack in cotton without using excessive pesticides?',
            'timestamp': (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S"),
            'responses': 7,
            'helpful_count': 25,
            'status': 'answered'
        },
        {
            'id': 'Q003',
            'farmer_name': 'Suresh Patel',
            'location': 'Gujarat',
            'crop_type': 'Groundnut',
            'category': 'Soil Management',
            'question': 'Best organic fertilizers for groundnut cultivation in sandy soil?',
            'timestamp': (datetime.now() - timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S"),
            'responses': 5,
            'helpful_count': 18,
            'status': 'answered'
        },
        {
            'id': 'Q004',
            'farmer_name': 'Lakshmi Devi',
            'location': 'Andhra Pradesh',
            'crop_type': 'Rice',
            'category': 'Water Management',
            'question': 'How to implement drip irrigation system for paddy cultivation?',
            'timestamp': (datetime.now() - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S"),
            'responses': 1,
            'helpful_count': 3,
            'status': 'open'
        },
        {
            'id': 'Q005',
            'farmer_name': 'Ramesh Reddy',
            'location': 'Karnataka',
            'crop_type': 'Tomato',
            'category': 'Market Information',
            'question': 'Current market rates for tomatoes in Bangalore wholesale market?',
            'timestamp': (datetime.now() - timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S"),
            'responses': 0,
            'helpful_count': 1,
            'status': 'open'
        }
    ]
    
    return posts

def generate_nearby_farmers(location, crop_interest):
    import random
    
    farmers = [
        {
            'name': 'Amit Singh',
            'location': location,
            'crops': ['Wheat', 'Mustard', 'Barley'],
            'experience': '15 years',
            'specialization': 'Organic farming',
            'contact': '+91 98xxx-xxxxx',
            'rating': 4.8,
            'distance': f"{random.randint(2, 15)} km"
        },
        {
            'name': 'Sunita Devi',
            'location': location,
            'crops': ['Rice', 'Vegetables', 'Pulses'],
            'experience': '12 years',
            'specialization': 'Sustainable agriculture',
            'contact': '+91 97xxx-xxxxx',
            'rating': 4.6,
            'distance': f"{random.randint(5, 20)} km"
        },
        {
            'name': 'Kiran Patil',
            'location': location,
            'crops': ['Cotton', 'Soybean', 'Maize'],
            'experience': '20 years',
            'specialization': 'Precision farming',
            'contact': '+91 96xxx-xxxxx',
            'rating': 4.9,
            'distance': f"{random.randint(8, 25)} km"
        },
        {
            'name': 'Deepak Yadav',
            'location': location,
            'crops': ['Sugarcane', 'Wheat', 'Potato'],
            'experience': '18 years',
            'specialization': 'Water management',
            'contact': '+91 95xxx-xxxxx',
            'rating': 4.7,
            'distance': f"{random.randint(3, 12)} km"
        }
    ]
    
    if crop_interest != 'All':
        farmers = [f for f in farmers if crop_interest in f['crops']]
    
    return random.sample(farmers, min(len(farmers), 6))





if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
