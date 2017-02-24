import os
from htdocs import webfaction


def application(environ, start_response):
    """
    transport any environment variables from the apache
    system into the flask wsgi application space
    """
    for key in environ:
        if key.startswith('MYAPP_'):
            os.environ[key] = environ[key]

    # import the flask application
    from myapp.main import app

    # load some middleware to append the current appname to /
    app.wsgi_app = webfaction.Middleware(app.wsgi_app)

    return app(environ, start_response)

