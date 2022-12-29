
# Henry the Hypemachine
The friendliest, most supportive and persuasive robot on Telegram.

Hosted on AWS EC2 using DynamoDB, built with Python, OpenAI & Telegram Bot APIs

## Local Deployment
1. Clone the repository and navigate to the directory

   ```bash
       gh repo clone Build-the-Bear/Henry && cd ./Henry
   ```

2. Create a new virtual environment

   ```bash
        python3 -m venv venv
        . venv/bin/activate
   ```

3. Install the requirements

   ```bash
        pip3 install -r requirements.txt
   ```

4. Make a copy of the example environment variables file

   ```bash
        .env.example .env
   ```

5. Add your [OpenAI API key](https://beta.openai.com/account/api-keys) to the newly created `.env` file 


6. Create your bot and add the [Telegram Bot API key](https://core.telegram.org/bots) to your `.env`, then make it an admin of at least one Telegram group


7. Create an AWS DynamoDB table named `chat_info` with `chat_id` as the primary key, and add your AWS account's access key(s) to the `.env` file as well


8. Run Henry!

   ```bash
        python3 henry.py
   ```

## Contributing

- Fork the repo and create a new branch, then make your changes
- Use title-case in your commit messages with a brief, comma-delimited list of changes
- Create a pull request to the 'dev' branch with a description of changes, and expected results
- Request review from Build-the-Bear

<hr>

[![MIT License](https://img.shields.io/badge/License-GNU%20General%20Public%20License%20v3.0-orange)](https://choosealicense.com/licenses/gpl-3.0/)
