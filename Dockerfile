# Use an official Python image
FROM python:3.10-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the file with the list of dependencies
COPY requirements.txt .

# Install the dependencies
# --no-cache-dir makes the image smaller
RUN pip install -r requirements.txt --no-cache-dir

# Copy the rest of your app's code (your bot.py)
COPY . .

# This is the command that will run when the container starts
CMD ["python", "bot.py"]