# SQL Mystery Game

A Streamlit-based interactive SQL mystery game with:
- Fake inventory supply chain database
- LLM-based SQL query generation with safety controls
- SQL evaluator and auto-scoring
- Adaptive difficulty based on student performance
- Comprehensive student logs and instructor dashboard
- Secure user authentication with role-based access
- Rate limiting and anti-cheating measures
- Detailed activity logging and analytics

## First-Time Setup

1. **Install Python Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Initialize the Database**
   ```bash
   python init_db.py
   ```
   This will:
   - Create a new SQLite database file (`game.db`)
   - Set up all required tables
   - Create a default admin instructor account:
     - Username: `admin`
     - Password: `admin123`

3. **Add Instructors (Optional)**
   - Start the app: `streamlit run app.py`
   - Log in as the admin user
   - Navigate to the signup page and create instructor accounts
   - Instructors will be available for student registration

## Regular Startup

To start the application after initial setup:

```bash
streamlit run app.py
```

## User Guide

### For Students
1. Sign up for an account, selecting your instructor from the dropdown
2. Complete SQL challenges to solve inventory mysteries
3. Use the AI assistant to generate SQL queries when needed (rate limited)
4. View your progress, past attempts, and feedback
5. Track your remaining daily query quota

### For Instructors
1. Log in with your credentials
2. Access the instructor dashboard to monitor all student progress
3. View detailed attempt logs, including SQL queries and results
4. Track completion rates and identify students needing help
5. Monitor LLM usage and query patterns
6. View system-wide analytics and performance metrics

## Security & Rate Limiting

The application includes several security measures:

- **Rate Limiting**: 
  - Students: 10 requests per 5 minutes, 100 requests per day
  - Instructors: 20 requests per 5 minutes, 200 requests per day
  - Burst protection: Max 3 rapid requests in 30 seconds

- **Content Filtering**:
  - AI responses are filtered for inappropriate content
  - Anti-cheating measures prevent solution sharing
  - All LLM interactions are logged and monitored

- **Data Protection**:
  - Secure password hashing
  - SQL injection prevention
  - Session management and CSRF protection

## Troubleshooting

### Common Issues

**Database Connection Issues**
```bash
# Reset the database (warning: deletes all data)
rm -f game.db
python init_db.py
```

**Rate Limit Reached**
- Wait a few minutes before making more requests
- Check your daily quota in the user interface
- Contact your instructor if you need a higher limit

**LLM Service Unavailable**
- Ensure Ollama service is running locally
- Check that the model is downloaded and accessible
- Verify network connectivity if using a remote LLM service

## Monitoring & Maintenance

Instructors can monitor system health and usage through the admin dashboard, including:
- Active user sessions
- System resource usage
- Error rates and performance metrics
- Security event logs
