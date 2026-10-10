[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=MakunaiGlobal_console-service&metric=coverage&token=fb98fc5c0efba8f095874d168395b0da94c60211)](https://sonarcloud.io/summary/new_code?id=MakunaiGlobal_console-service)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=MakunaiGlobal_console-service&metric=alert_status&token=fb98fc5c0efba8f095874d168395b0da94c60211)](https://sonarcloud.io/summary/new_code?id=MakunaiGlobal_console-service)
[![Bugs](https://sonarcloud.io/api/project_badges/measure?project=MakunaiGlobal_console-service&metric=bugs&token=fb98fc5c0efba8f095874d168395b0da94c60211)](https://sonarcloud.io/summary/new_code?id=MakunaiGlobal_console-service)
[![Code Smells](https://sonarcloud.io/api/project_badges/measure?project=MakunaiGlobal_console-service&metric=code_smells&token=fb98fc5c0efba8f095874d168395b0da94c60211)](https://sonarcloud.io/summary/new_code?id=MakunaiGlobal_console-service)
[![Duplicated Lines (%)](https://sonarcloud.io/api/project_badges/measure?project=MakunaiGlobal_console-service&metric=duplicated_lines_density&token=fb98fc5c0efba8f095874d168395b0da94c60211)](https://sonarcloud.io/summary/new_code?id=MakunaiGlobal_console-service)

[![Lines of Code](https://sonarcloud.io/api/project_badges/measure?project=MakunaiGlobal_console-service&metric=ncloc&token=fb98fc5c0efba8f095874d168395b0da94c60211)](https://sonarcloud.io/summary/new_code?id=MakunaiGlobal_console-service)
[![Reliability Rating](https://sonarcloud.io/api/project_badges/measure?project=MakunaiGlobal_console-service&metric=reliability_rating&token=fb98fc5c0efba8f095874d168395b0da94c60211)](https://sonarcloud.io/summary/new_code?id=MakunaiGlobal_console-service)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=MakunaiGlobal_console-service&metric=security_rating&token=fb98fc5c0efba8f095874d168395b0da94c60211)](https://sonarcloud.io/summary/new_code?id=MakunaiGlobal_console-service)
[![Technical Debt](https://sonarcloud.io/api/project_badges/measure?project=MakunaiGlobal_console-service&metric=sqale_index&token=fb98fc5c0efba8f095874d168395b0da94c60211)](https://sonarcloud.io/summary/new_code?id=MakunaiGlobal_console-service)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=MakunaiGlobal_console-service&metric=sqale_rating&token=fb98fc5c0efba8f095874d168395b0da94c60211)](https://sonarcloud.io/summary/new_code?id=MakunaiGlobal_console-service)
[![Vulnerabilities](https://sonarcloud.io/api/project_badges/measure?project=MakunaiGlobal_console-service&metric=vulnerabilities&token=fb98fc5c0efba8f095874d168395b0da94c60211)](https://sonarcloud.io/summary/new_code?id=MakunaiGlobal_console-service)

# Project Setup Guide

This guide outlines the steps to set up the project environment, including creating directories, cloning the GitHub repository, managing Docker containers, and optimizing the process through efficient SSH key management.

##
## Create a Directory and Navigate to It :
1. Create a new directory named `maglo`:

    ```bash
        mkdir maglo
2. Navigate to the newly created directory:
    ```bash
        cd maglo
##
## Clone the repository from GitHub using SSH:
        git clone git@github.com:MakunaiGlobal/console-service.git


Navigate to the Cloned Repository

        cd console-service/
##
## Docker setup

- Install docker : -    https://docs.docker.com/engine/install/

 For Windows Users:
1. Go to the control panel and enable the WSL feature.
2. Install the latest version of Linux (Ubuntu) from the Microsoft Store.
3. Restart your system.
4. Open Ubuntu.


Open the Docker and Ubuntu terminal and run the following command (the first time):

		docker-compose up -–build


Start Docker Containers Using docker-compose

            docker-compose up



To run the Docker containers in the background, use:
        docker-compose up -d

Check the status of the containers:

        docker-compose ps
##
# SSH Key Management Guide

This guide outlines steps to efficiently manage SSH keys for secure access to GitHub repositories.
### 5.1. SSH Key Management

To ensure a smooth and secure process when cloning repositories, it's essential to have your SSH key properly configured.

- **Add your SSH key to GitHub**: Before cloning repositories, make sure your SSH key is added to your GitHub account to avoid connection issues.
- **Use a passphrase**: Adding a passphrase to your SSH key enhances security.

### 5.2. Generate an SSH Key

Follow these steps to generate a new SSH key if you don't already have one:

#### 5.2.1. Generate a new SSH key

Run the following command in your terminal:

            ssh-keygen


#### 5.3. Copy the SSH Public Key

After generating your SSH key, you'll need to copy the public key to GitHub.

```bash
        cat ~/.ssh/id_rsa.pub
