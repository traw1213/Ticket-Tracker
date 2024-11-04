import datetime
import statistics
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify

app = Flask(__name__)
app.secret_key = 'supersecretkey'

tickets = []  # List to store ticket data
work_sessions = []  # List to store work session data
daily_logs = []  # List to store daily work logs
work_timer = {'start_time': None, 'paused_time': None, 'total_seconds_worked': 0}  # Work timer to track active work time
travel_timer = {'start_time': None, 'total_travel_time': 0}  # Travel timer to track travel time between tickets

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        action = request.form.get('action')
        ticket_id = request.form.get('ticket_id')
        timestamp = datetime.datetime.now()

        if action == 'add_ticket':
            # Get ticket information from the form
            ticket_description = request.form['ticket_description']
            # Check if the ticket description already exists
            existing_ticket = next((ticket for ticket in tickets if ticket['description'] == ticket_description), None)
            if existing_ticket:
                return render_template('confirm.html', ticket_description=ticket_description)
            else:
                # Append new ticket data with arrival time
                tickets.append({'id': len(tickets), 'description': ticket_description, 'timestamp': timestamp, 'arrival_time': timestamp, 'completion_time': None})
                # End travel time when new ticket is added
                if travel_timer['start_time']:
                    travel_timer['total_travel_time'] += (timestamp - travel_timer['start_time']).total_seconds()
                    travel_timer['start_time'] = None

        elif ticket_id is not None and ticket_id.isdigit():
            ticket_id = int(ticket_id)
            if ticket_id < len(tickets):
                if action == 'complete' and work_timer['start_time']:
                    # Log completion time
                    tickets[ticket_id]['completion_time'] = timestamp
                    # Start travel timer
                    travel_timer['start_time'] = timestamp
                    # Update tickets per hour calculation on ticket completion
                    update_tph()
                    return redirect(url_for('index'))
                elif action == 'cancel' and work_timer['start_time']:
                    # Cancel ticket
                    tickets[ticket_id]['completion_time'] = 'Cancelled'
                    # Update tickets per hour calculation on ticket cancellation
                    update_tph()
                elif action == 'delete':
                    # Delete ticket
                    tickets.pop(ticket_id)
                    # Update tickets per hour calculation after deletion
                    update_tph()
                    return redirect(url_for('index'))
        elif action == 'start_work' and not work_timer['start_time']:
            # Start work session
            work_sessions.append({'action': action, 'timestamp': timestamp})
            work_timer['start_time'] = timestamp
        elif action == 'end_work' and work_timer['start_time']:
            # End work session
            work_sessions.append({'action': action, 'timestamp': timestamp})
            work_timer['total_seconds_worked'] += (timestamp - work_timer['start_time']).total_seconds()
            work_timer['start_time'] = None
            # Log daily data
            log_daily_data(timestamp)
            # Update tickets per hour calculation on ending work
            update_tph()
        elif action == 'start_meal' and work_timer['start_time']:
            # End travel time when starting a meal break
            if travel_timer['start_time']:
                travel_timer['total_travel_time'] += (timestamp - travel_timer['start_time']).total_seconds()
                travel_timer['start_time'] = None
            # Pause work session for meal
            work_sessions.append({'action': action, 'timestamp': timestamp})
            work_timer['total_seconds_worked'] += (timestamp - work_timer['start_time']).total_seconds()
            work_timer['paused_time'] = timestamp
            work_timer['start_time'] = None
        elif action == 'end_meal' and work_timer['paused_time']:
            # Resume travel timer if applicable after meal break
            if travel_timer['start_time'] is None:
                travel_timer['start_time'] = timestamp
            # Resume work session after meal
            work_sessions.append({'action': action, 'timestamp': timestamp})
            work_timer['start_time'] = timestamp
            work_timer['paused_time'] = None

    # Group tickets by hour
    tickets_per_hour = {}
    for ticket in tickets:
        hour = ticket['timestamp'].strftime('%Y-%m-%d %H:00')
        if hour not in tickets_per_hour:
            tickets_per_hour[hour] = 0
        tickets_per_hour[hour] += 1

    # Calculate current timer duration
    current_timer_duration = work_timer['total_seconds_worked']
    if work_timer['start_time']:
        current_timer_duration += (datetime.datetime.now() - work_timer['start_time']).total_seconds()

    current_timer_duration_str = str(datetime.timedelta(seconds=int(current_timer_duration)))

    # Calculate current travel time duration
    current_travel_duration = travel_timer['total_travel_time']
    if travel_timer['start_time']:
        current_travel_duration += (datetime.datetime.now() - travel_timer['start_time']).total_seconds()

    current_travel_duration_str = str(datetime.timedelta(seconds=int(current_travel_duration)))

    return render_template('index.html', tickets=tickets, tickets_per_hour=tickets_per_hour, work_sessions=work_sessions, tickets_per_hour_live=work_timer.get('tickets_per_hour_live', 0), current_timer_duration=current_timer_duration_str, work_timer=work_timer, current_travel_duration=current_travel_duration_str)

# New Route to Handle Ticket Confirmation
@app.route('/confirm', methods=['POST'])
def confirm():
    ticket_description = request.form['ticket_description']
    action = request.form.get('confirm_work')

    if action == 'yes':
        # Create a new entry for working on the same ticket again
        timestamp = datetime.datetime.now()
        tickets.append({'id': len(tickets), 'description': ticket_description, 'timestamp': timestamp, 'arrival_time': timestamp, 'completion_time': None})
        return redirect(url_for('index'))
    elif action == 'no':
        return redirect(url_for('index'))

    return redirect(url_for('index'))

def log_daily_data(end_time):
    completed_tickets = [ticket for ticket in tickets if ticket['completion_time'] and ticket['completion_time'] != 'Cancelled']
    total_travel_time = travel_timer['total_travel_time']
    total_work_time = work_timer['total_seconds_worked']
    daily_logs.append({
        'date': end_time.date(),
        'tickets_completed': len(completed_tickets),
        'total_work_time': total_work_time,
        'total_travel_time': total_travel_time,
        'tph': work_timer['tickets_per_hour_live']
    })
    # Reset work and travel timers
    work_timer['total_seconds_worked'] = 0
    travel_timer['total_travel_time'] = 0

@app.route('/logs', methods=['GET'])
def logs():
    time_frame = request.args.get('time_frame', 'all')
    filtered_logs = filter_logs(time_frame)

    # Calculate rolling averages
    rolling_tickets = statistics.mean([log['tickets_completed'] for log in filtered_logs]) if filtered_logs else 0
    rolling_tph = statistics.mean([log['tph'] for log in filtered_logs]) if filtered_logs else 0
    rolling_travel_time = statistics.mean([log['total_travel_time'] for log in filtered_logs]) if filtered_logs else 0

    return render_template('logs.html', daily_logs=filtered_logs, rolling_tickets=rolling_tickets, rolling_tph=rolling_tph, rolling_travel_time=rolling_travel_time, time_frame=time_frame)

def filter_logs(time_frame):
    now = datetime.datetime.now()
    if time_frame == 'weekly':
        start_date = now - datetime.timedelta(weeks=1)
    elif time_frame == 'monthly':
        start_date = now - datetime.timedelta(days=30)
    elif time_frame == '3_months':
        start_date = now - datetime.timedelta(days=90)
    elif time_frame == '6_months':
        start_date = now - datetime.timedelta(days=180)
    elif time_frame == 'yearly':
        start_date = now - datetime.timedelta(days=365)
    else:
        return daily_logs

    return [log for log in daily_logs if datetime.datetime.combine(log['date'], datetime.datetime.min.time()) >= start_date]

@app.route('/get_tph', methods=['GET'])
def get_tph():
    return jsonify({'tickets_per_hour_live': work_timer.get('tickets_per_hour_live', 0)})

@app.template_filter('calculate_duration')
def calculate_duration(ticket):
    if ticket['arrival_time'] and ticket['completion_time'] and ticket['completion_time'] != 'Cancelled':
        duration = ticket['completion_time'] - ticket['arrival_time']
        return str(duration)
    return "N/A"

@app.template_filter('timedelta')
def timedelta_filter(seconds):
    return str(datetime.timedelta(seconds=int(seconds)))

def update_tph():
    completed_tickets = [ticket for ticket in tickets if ticket['completion_time'] and ticket['completion_time'] != 'Cancelled']
    total_seconds_worked = work_timer['total_seconds_worked']
    if work_timer['start_time']:
        total_seconds_worked += (datetime.datetime.now() - work_timer['start_time']).total_seconds()

    total_hours_worked = total_seconds_worked / 3600

    if total_hours_worked < 1:
        # If within the first hour, TPH is simply the number of completed tickets
        work_timer['tickets_per_hour_live'] = len(completed_tickets)
    else:
        # After the first hour, TPH is calculated as tickets completed divided by hours worked
        work_timer['tickets_per_hour_live'] = len(completed_tickets) / total_hours_worked

if __name__ == '__main__':
    app.run(debug=True)
