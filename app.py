import pandas as pd
import matplotlib.pyplot as plt
from statsmodels.tsa.arima.model import ARIMA
import psycopg2
from psycopg2 import sql
from flask import Flask, render_template, request, redirect, url_for, flash, session

app = Flask(__name__)
app.secret_key = 'my_health'

# Database connection settings
DB_NAME = "Health"
DB_USER = "postgres"
DB_PASS = "root"

# Connect to PostgreSQL
def get_db_connection():
    conn = psycopg2.connect(database=DB_NAME, user=DB_USER, password=DB_PASS)
    return conn

# Function to handle NaN values
def treat_none_values(dataset, t_method='row'):
    if t_method == 'row':
        cleaned_dataset = dataset.fillna("not")  # Fill NaNs with 'not'
    else:
        raise ValueError("t_method should be 'row'.")
    return cleaned_dataset

# Function to select specific columns and reset the index
def select_columns_from_dataset(columns_to_keep, dataset):
    cleaned_dataset = dataset[columns_to_keep].reset_index(drop=True)
    cleaned_dataset['Date'] = pd.to_datetime(cleaned_dataset['Date']).dt.date  # Convert 'Date' column to date format
    return cleaned_dataset

# Function to aggregate medication demand on a monthly basis
def aggregate_medication_demand_monthly(dataset):
    dataset['Date'] = pd.to_datetime(dataset['Date'])
    dataset['year_month'] = dataset['Date'].dt.to_period('M')  # Extract year and month
    aggregated_dataset = dataset.groupby(['Medication Name', 'year_month'], as_index=False)['Medication Demand'].sum()
    aggregated_dataset = aggregated_dataset.sort_values(by=['year_month', 'Medication Name'])
    return aggregated_dataset

# Function to forecast medication demand using ARIMA
def forecast_medication_demand(data, steps=6):
    unique_medications = data['Medication Name'].unique()
    forecasts_list = []

    for medication in unique_medications:
        medication_data = data[data['Medication Name'] == medication]
        medication_data = medication_data.set_index('year_month')
        medication_data.index = medication_data.index.to_timestamp()

        try:
            model = ARIMA(medication_data['Medication Demand'], order=(1, 1, 1))
            model_fit = model.fit()
            forecast = model_fit.forecast(steps=steps)
            forecast = forecast.round().astype(int)  # Round forecast values to integers

            # Generate the forecast index
            last_date = medication_data.index[-1]
            forecast_index = pd.date_range(start=last_date + pd.DateOffset(months=1), periods=steps, freq='M')
            forecast.index = forecast_index

            # Store forecast data
            forecast_data = {
                'medication_name': medication,
                'First_month_Forecast': forecast[0] if len(forecast) > 0 else None,
                'Second_month_Forecast': forecast[1] if len(forecast) > 1 else None,
                'Third_month_Forecast': forecast[2] if len(forecast) > 2 else None,
                'Fourth_month_Forecast': forecast[3] if len(forecast) > 3 else None,
                'Fifth_month_Forecast': forecast[4] if len(forecast) > 4 else None,
                'Six_month_Forecast': forecast[5] if len(forecast) > 5 else None
            }
            forecasts_list.append(forecast_data)

            # Plotting the forecast
            plt.figure(figsize=(10, 6))
            plt.plot(medication_data.index, medication_data['Medication Demand'], label='Historical Data')
            plt.plot(forecast.index, forecast, label='Forecast', color='red')
            plt.xlabel('Month')
            plt.ylabel('Medication Demand')
            plt.title(f'Medication Demand Forecast for {medication}')
            plt.legend()
            plt.show()

        except Exception as e:
            print(f"ARIMA model could not be fitted for {medication}. Error: {e}")

    # Create a DataFrame from the forecast list
    forecast_df = pd.DataFrame(forecasts_list)
    return forecast_df

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        clinic_id = request.form['clinic_id']
        password = request.form['password']

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(sql.SQL("SELECT * FROM clinics WHERE clinic_id = %s AND password = %s"), (clinic_id, password))
        clinic = cur.fetchone()
        cur.close()
        conn.close()

        if clinic:
            session['clinic_id'] = clinic_id
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials, please try again.')

    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'clinic_id' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html')

@app.route('/add_data', methods=['GET', 'POST'])
def add_data():
    if 'clinic_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        clinic_id = session['clinic_id']
        table_name = f'{clinic_id}_medication_data'  # Correctly format table name

        date = request.form['date']
        patient_name = request.form['patient_name']
        patient_age = request.form['patient_age']
        patient_gender = request.form['patient_gender']
        chronic_condition = request.form['chronic_condition']
        appointment_type = request.form['appointment_type']
        
        medication_name = request.form['medication_name']
        medication_demand = request.form['medication_demand']

        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                sql.SQL("INSERT INTO {} (Date, Patient_name, Patient_age, Patient_gender, Chronic_condition, Appointment_type,Medication_Name, Medication_Demand) VALUES (%s, %s, %s, %s, %s, %s , %s, %s)")
                .format(sql.Identifier(table_name)),
                (date, patient_name, patient_age, patient_gender, chronic_condition, appointment_type, medication_name, medication_demand)
            )
            conn.commit()
            flash('Data added successfully!')
        except psycopg2.errors.UndefinedTable as e:
            flash(f'Error: Table does not exist. {e}')
        except Exception as e:
            flash(f'Error: {e}')
        finally:
            cur.close()
            conn.close()

        return redirect(url_for('dashboard'))
    
    return render_template('add_data.html')

@app.route('/display_data', methods=['GET'])
def display_data():
    if 'clinic_id' not in session:
        return redirect(url_for('login'))

    clinic_id = session['clinic_id']
    table_name = f'{clinic_id}_medication_data'  # Use the correct table for each clinic

    search_query = request.args.get('search', '')  # Get the search query from the URL

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        if search_query:
            # Run a case-insensitive search on relevant columns (e.g., Patient_name, Medication_Name)
            search_pattern = f"%{search_query}%"
            query = sql.SQL("SELECT * FROM {} WHERE Patient_name ILIKE %s OR Medication_Name ILIKE %s").format(sql.Identifier(table_name))
            cur.execute(query, (search_pattern, search_pattern))
        else:
            # If no search query, fetch all the data
            query = sql.SQL("SELECT * FROM {}").format(sql.Identifier(table_name))
            cur.execute(query)
        
        rows = cur.fetchall()

        # Convert the result to a DataFrame for rendering
        df = pd.DataFrame(rows, columns=['Date', 'Patient_name', 'Patient_age', 'Patient_gender', 'Chronic_condition', 'Appointment_type', 'Medication_Name', 'Medication_Demand'])
        df['Date'] = pd.to_datetime(df['Date']).dt.date  # Convert date to a readable format

    except psycopg2.errors.UndefinedTable as e:
        flash(f'Error: Table does not exist. {e}')
        df = pd.DataFrame()  # Return empty dataframe in case of an error
    except Exception as e:
        flash(f'Error: {e}')
        df = pd.DataFrame()
    finally:
        cur.close()
        conn.close()

    return render_template('display_data.html', data=df.to_html(classes='data', header="true"))


'''@app.route('/logout')
def logout():
    session.pop('clinic_id', None)
    return redirect(url_for('login'))
'''
@app.route('/predict_demand')
def predict_demand():
    if 'clinic_id' not in session:
        return redirect(url_for('login'))

    clinic_id = session['clinic_id']
    table_name = f'{clinic_id}_medication_data'  # Correctly format table name

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(sql.SQL("SELECT  date, medication_name, medication_demand FROM {}").format(sql.Identifier(table_name)))
        rows = cur.fetchall()

        # Load data into DataFrame
        df = pd.DataFrame(rows, columns=['Date', 'Medication Name', 'Medication Demand'])

        # Clean the dataset
        df = treat_none_values(df, t_method='row')
        df = select_columns_from_dataset(['Date', 'Medication Name', 'Medication Demand'], df)
        df = aggregate_medication_demand_monthly(df)

        forecast_df = forecast_medication_demand(df)
        forecast_data = forecast_df.to_dict(orient='records')

    except psycopg2.errors.UndefinedTable as e:
        flash(f'Error: Table does not exist. {e}')
        forecast_data = []
    except Exception as e:
        flash(f'Error: {e}')
        forecast_data = []
    finally:
        cur.close()
        conn.close()

    return render_template('predict_demand.html', forecasts=forecast_data)

@app.route('/logout')
def logout():
    session.pop('clinic_id', None)
    return redirect(url_for('login'))

import os


# Ensure the directory for saving images exists
os.makedirs('static/forecast_plots', exist_ok=True)

def forecast_medication_demand(data, steps=6):
    unique_medications = data['Medication Name'].unique()
    forecasts_list = []

    for medication in unique_medications:
        medication_data = data[data['Medication Name'] == medication]
        medication_data = medication_data.set_index('year_month')
        medication_data.index = medication_data.index.to_timestamp()

        try:
            model = ARIMA(medication_data['Medication Demand'], order=(1, 1, 1))
            model_fit = model.fit()
            forecast = model_fit.forecast(steps=steps)
            forecast = forecast.round().astype(int)  # Round forecast values to integers

            # Generate the forecast index
            last_date = medication_data.index[-1]
            forecast_index = pd.date_range(start=last_date + pd.DateOffset(months=1), periods=steps, freq='M')
            forecast.index = forecast_index

            # Store forecast data
            forecast_data = {
                'medication_name': medication,
                'First_month_Forecast': forecast[0] if len(forecast) > 0 else None,
                'Second_month_Forecast': forecast[1] if len(forecast) > 1 else None,
                'Third_month_Forecast': forecast[2] if len(forecast) > 2 else None,
                'Fourth_month_Forecast': forecast[3] if len(forecast) > 3 else None,
                'Fifth_month_Forecast': forecast[4] if len(forecast) > 4 else None,
                'Six_month_Forecast': forecast[5] if len(forecast) > 5 else None,
                'plot_path': f'static/forecast_plots/{medication}.png'  # Path for the plot image
            }
            forecasts_list.append(forecast_data)

            # Save the plot as an image
            plt.figure(figsize=(10, 6))
            plt.plot(medication_data.index, medication_data['Medication Demand'], label='Historical Data')
            plt.plot(forecast.index, forecast, label='Forecast', color='red')
            plt.xlabel('Month')
            plt.ylabel('Medication Demand')
            plt.title(f'Medication Demand Forecast for {medication}')
            plt.legend()
            plt.savefig(f'static/forecast_plots/{medication}.png')  # Save plot
            plt.close()  # Close the plot

        except Exception as e:
            print(f"ARIMA model could not be fitted for {medication}. Error: {e}")

    # Create a DataFrame from the forecast list
    forecast_df = pd.DataFrame(forecasts_list)
    return forecast_df

if __name__ == '__main__':
    app.run(debug=True)
