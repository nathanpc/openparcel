# OpenParcel

An initiative to create an open source parcel tracking API and library that
only uses public resources, no private access tokens or special contracts
required.

## Setup

First let's set up the environment in order to run our server. Start by creating
a Python virtual environment and installing the project's dependencies into it:

```shell
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Next we need to create a configuration file. This can be done by duplicating the
example `config/config.example.yml` into `config/config.yml` and generating an
appropriate encryption key for the session cookie storage:

```shell
cp config/config.example.yml config/config.yml
sed -i '' -r "s/SECRET_KEY.+/SECRET_KEY: '$(python -c 'import secrets; print(secrets.token_hex())')'/" config/config.yml
cat config/config.yml
```

Ensure that the `SECRET_KEY` value was properly set to a strong encryption key.
Then to the initialization of the database using the `sql/initialize.sql`. This
can be achieved using the following command:

```shell
sqlite3 openparcel.db < sql/initialize.sql
```

Now all that's left for you to do is start the server up and test it out!

```shell
flask run
```

## License

This library is free software; you may redistribute and/or modify it under the
terms of the [Mozilla Public License 2.0](https://www.mozilla.org/en-US/MPL/2.0/).
