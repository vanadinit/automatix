# TESTING

## Docker setup for integration tests

* Install docker and docker-compose
* Install pytest and pytest-docker-compose via pip
* Generate a ssh keypair and place it in tests with `ssh-keygen -t rsa -f tests/id_rsa_tests`
* In tests: Copy docker-compose.example.yml to docker-compose.yml and replace the public key
* Put something like the following in your ~.ssh/config


    Host docker-test
    Hostname localhost
    Port 2222
    IdentityFile tests/id_rsa_tests
    StrictHostKeyChecking no
    

* Run `make test` in the automatix root directory.