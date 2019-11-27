#!/bin/bash

# Copyright (c) 2018, WSO2 Inc. (http://wso2.com) All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# This script is to clone the product repo from the support branch. The clone will be doing by passing the ssh key.

# Add github key to known host
ssh-keyscan -H "github.com" >> ~/.ssh/known_hosts

# Start the ssh-agent
eval "$(ssh-agent -s)"

# Write ssh key to id-rsa file and set the permission
echo "$1" > ~/.ssh/id_rsa
username=$(id -un)

if [ $username == "centos" ]; then
    chmod 600 /home/centos/.ssh/id_rsa
else
    chmod 600 /home/ubuntu/.ssh/id_rsa
fi

# Add ssh key to the agent
ssh-add ~/.ssh/id_rsa

# List fingerprints of all identities
ssh-add -l

# clone the specified branch of the specified product repository
ssh-agent bash -c "ssh-add ~/.ssh/id_rsa; git clone --single-branch --branch $2 $3"
