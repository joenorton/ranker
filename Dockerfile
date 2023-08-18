FROM python:3.9.17-alpine3.18
# Or any preferred Python version.

COPY . /app
WORKDIR /app

# Install & use pipenv
RUN pip install pipenv
RUN pip install importlib-metadata

RUN pipenv install --system --deploy

CMD ["python3", "-m" , "flask", "run", "--host=0.0.0.0"]
