# import packages
import requests
import logging
import random
import openai
import boto3
import time
import ast
import os

from henryPrompts import randomPrompts, randomMessages, triggerMessages
from boto3.dynamodb.conditions import Key
from dotenv import load_dotenv

# load environment variables
load_dotenv('./.env')

openai.api_key = os.getenv('OPENAI_API_KEY')

# define environment variables
lastUpdateID = -1 # offset response from getTelegramUpdates
lastChatIDs = [0, 0, 0] # chat IDs for the last few messages, to prevent flooding
existingChats = {} # e.g. {-1001640903207: "Last message sent"}
existingReplies = {} # e.g. {-1001640903207: [100, 250, 3000]}

# connect to dynamodb on aws
dynamodb = boto3.resource('dynamodb', aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID'),
                                  aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY'), region_name='us-east-2')
chatInfo = dynamodb.Table('chat_info')
# chatInfo = dynamodb.Table('henry_test_chat_information')

# designate log location
logging.basicConfig(filename='henry.log', level=logging.INFO)

# fetch existing chats_ids from aws
def getExistingChatInformation():
    response = chatInfo.scan()

    for i in response['Items']:
        if 'last_reply' in i and i['last_reply'] is not None:
            existingChats[i['chat_id']] = i['last_reply']
        else:
            existingChats[i['chat_id']] = ""
        existingReplies[str(i['chat_id'])] = ast.literal_eval(i['chat_replies'])

# fetch recent updates from telegram
def getTelegramUpdates():
    global lastUpdateID

    # offset by last updates retrieved
    url = 'https://api.telegram.org/' + os.getenv('PROD_TELEGRAM_API_KEY') + '/getupdates?offset=' + str(lastUpdateID + 1)
    updates = requests.get(url)
    response = updates.json()['result']

    # logging.info(response)

    if len(response):
        lastUpdateID = response[len(response) - 1]['update_id']

    for i in response:# if we see henry has been added to any new chats, add the chat_id to our database
        if "my_chat_member" in i and i['my_chat_member']['new_chat_member']['user']['first_name'] == 'Henry the Hypemachine':
            isGroupChat(i['my_chat_member']['chat']['id'])

        # check new messages
        if "message" in i and "text" in i['message']:
            checkForNewChatID(i['message']['chat']['id'])

            # if henry was replied to directly
            if "reply_to_message" in i['message'] and i['message']['reply_to_message']['from']['username'].startswith('Henrythe'):
                henryReplies(i['message']['text'], i['message']['chat']['id'], i['message']['message_id'])

            # if any-case match was found for one of henry's triggers, and he hasn't already, tell him to respond
            for j in triggerMessages:
                matchFound = False

                if j in i['message']['text'] or j.lower() in i['message']['text'] or j.upper() in i['message']['text']:
                    matchFound = True
                if matchFound and i['message']['message_id'] not in existingReplies[str(i['message']['chat']['id'])]:
                    triggerResponse(i['message']['chat']['id'], i['message']['message_id'], j)

# conditionally save a new chat_id
def checkForNewChatID(chatID):
    if chatID not in existingChats:
        existingChats[chatID] = ""
        existingReplies[str(chatID)] = [0, 1]

        chatInfo.put_item(Item={'chat_id': chatID, 'chat_replies': str([0, 1])})

# make sure we're not saving user chats
def isGroupChat(chatID):
    try:
        url = 'https://api.telegram.org/' + os.getenv('PROD_TELEGRAM_API_KEY') + '/getChat?chat_id=' + str(chatID)
        updates = requests.get(url)

        if len(updates.json()['result']['type']) : type = updates.json()['result']['type']

        if type != "private": return True
        else: return False
    except requests.exceptions.HTTPError as err:
        logging.info("Henry was met with a closed door: " + err)

# trigger unique responses based on direct replies to henry
def henryReplies(toMessage, chatID, messageID):
    cid = str(chatID)
    # season henry's output with cyborg stock
    mess = spice(toMessage, True, "Reply to the following using the voice of a king from the 1500s. Be confident, optimistic, extremely brief, and as creative as possible. You must respond with complete sentences.")

    if existingChats[chatID] != mess and mess != "":
        sendResponse(chatID, messageID, mess)

# trigger unique responses by keyword
def triggerResponse(chatID, messageID, trigger):
    sendIt = True
    # season henry's output with cyborg stock
    mess = spice(random.choice(triggerMessages[trigger]), False, "")

    # prevent flooding an individual chat
    if lastChatIDs[0] == chatID and lastChatIDs[1] == chatID and lastChatIDs[2] == chatID:
        sendIt = False

    if existingChats[chatID] != mess and mess != "" and sendIt:
        sendResponse(chatID, messageID, mess)

def sendResponse(chatID, messageID, message):
    cid = str(chatID)
    mid = str(messageID)

    try:
        existingChats[chatID] = message

        url = 'https://api.telegram.org/' + os.getenv('PROD_TELEGRAM_API_KEY') + '/sendMessage?chat_id=' + cid + '&reply_to_message_id=' + mid + '&text=' + message
        x = requests.post(url, json={})

        time.sleep(10) #prevent api blacklisting

        # update local and database lists with new messageID
        replies = existingReplies[cid]
        replies.append(messageID)

        updateDatabase(chatID, replies, message)

        lastChatIDs.pop(0)
        lastChatIDs.append(chatID)

        logging.info("Henry had some words to say in Chat: " + cid + ": " + message)
    except requests.exceptions.HTTPError as err:
        logging.info("Henry was met with a closed door: " + err)

# trigger random responses
def sendRandomMessage():
    sendIt = True
    chatID = random.choice(list(existingChats))
    mess = spice(random.choice(randomMessages), False, "")

    while isGroupChat(chatID) != True and mess != "":
        chatID = random.choice(list(existingChats))

    # prevent flooding an individual chat
    if lastChatIDs[0] == chatID and lastChatIDs[1] == chatID and lastChatIDs[2] == chatID:
        sendIt = False

    if existingChats[chatID] != mess and mess != "" and sendIt:
        try:
            url = 'https://api.telegram.org/' + os.getenv('PROD_TELEGRAM_API_KEY') + '/sendMessage?chat_id=' + str(chatID) + '&text=' + mess
            x = requests.post(url, json={})

            updateDatabase(chatID, existingReplies[str(chatID)], mess)

            lastChatIDs.pop(0)
            lastChatIDs.append(chatID)

            logging.info("Henry had some words to say in Chat: " + str(chatID) + ": " + mess)
        except requests.exceptions.HTTPError as err:
            logging.info("Henry was met with a closed door: " + err)

# artificial seasoning
def spice(message, isReply, optionalPrompt):
    # if no specific prompt was provided, choose a random one
    if optionalPrompt == "":
        optionalPrompt = random.choice(randomPrompts)

    # season the prompt
    response = openai.Completion.create(
      model = "text-davinci-002",
      prompt = optionalPrompt + "\n\n'" + message + "'",
      temperature = 1.1,
      max_tokens = 50,
      top_p = 1,
      frequency_penalty = 0.9,
      presence_penalty = 0.9,
    )

    # for the memes
    mess = response.choices[0].text.replace("ors", "ooors")

    # clean up the presentation
    if mess[0] == '"' and mess[-1] == '"':
        mess = mess[1:]
        mess = mess[:-1]

    if isReply == False:
        # only reply 60% of the time Henry gets triggered
        r = random.randint(1, 10)
        if r > 6 : mess = ""

    return mess

# update database
def updateDatabase(chatID, replies, lastReply):
    try:
        response = chatInfo.update_item(
            Key={
                'chat_id': chatID,
            },
            UpdateExpression="set #chat_replies=:r, #last_reply=:l",
            ExpressionAttributeNames={
                '#chat_replies': 'chat_replies',
                '#last_reply': 'last_reply',
            },
            ExpressionAttributeValues={
                ':r': str(replies),
                ':l': lastReply,
            },
            ReturnValues="UPDATED_NEW"
        )
    except requests.exceptions.HTTPError as err:
        logging.info("Henry was met with a closed door: " + err)

# initialize
if __name__ == '__main__':
    # get existing chat information and new updates off the rip
    getExistingChatInformation()
    getTelegramUpdates()

    # spread some cheer
    if len(list(existingChats)) : sendRandomMessage()

    # set up update-check & trigger-message cycle
    runningTime, oneDaysTime = 0, 43200
    cycleTime = (oneDaysTime / 1) / (len(existingChats) + 1)

    # while running
    while runningTime < oneDaysTime:
        runningTime += 10

        # if it's time to spread more cheer
        if runningTime >= cycleTime :
            sendRandomMessage()
            runningTime = 0
        # else : logging.info("Carrying on, nothing new.. %i %i", runningTime, cycleTime)

        # wait before continuing to check for updates
        time.sleep(10)

        getExistingChatInformation()
        getTelegramUpdates()