# OpenParcel

An initiative to create an open source parcel tracking API and library that
only uses public resources, no private access tokens or special contracts
required.

## Requirements

Given the fact that this project was built from the ground up using modern tools
in order to take advantage of newer features and a better development experience
the minimum requirements for running the project may be a bit high.

- [Python 3.11](https://docs.python.org/3/whatsnew/3.11.html) or newer
- [SQLite 3.38.0](https://sqlite.org/releaselog/3_38_0.html) or newer

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

This library and service is free and its source is available under the
[Server Side Public License (SSPL) v1](https://spdx.org/licenses/SSPL-1.0.html),
allowing personal use that respects your privacy (self hosting) while ensuring
it is not exploited by comercial entities.

