# Henry the Hypemachine - Order of Events:
    # 1. Potentially sendRandomMessage
    # 2. Parse response from getTelegramUpdates
    # 3. Respond to mentions
    # 4. Respond to commands
    # 5. Respond to interesting threads, then messages

# import packages
import requests
import logging
import random
import openai
import boto3
import math
import time
import ast
import os

from henryPrompts import *
from boto3.dynamodb.conditions import Key
from dotenv import load_dotenv

# load environment variables
load_dotenv("./.env")

# set up API keys
telegramAPIKey = os.getenv("PROD_TELEGRAM_API_KEY")
openai.api_key = os.getenv("OPENAI_API_KEY")

# connect to dynamodb on aws
dynamodb = boto3.resource("dynamodb", aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID"),
                                  aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY"), region_name = "us-east-2")
chatInfo = dynamodb.Table('chat_info')

if telegramAPIKey == os.getenv('DEV_TELEGRAM_API_KEY'):
    chatInfo = dynamodb.Table("henry_test_chat_information")

# designate log location
logging.basicConfig(filename="henry.log", level=logging.INFO)

# define environment variables
lastUpdateID = -1  # offset response from getTelegramUpdates
lastChatIDs = [0, 0, 0]  # chat IDs for the last few messages, to prevent flooding
existingChats = {}  # e.g. {-1001640903207: "Last message sent"}
existingReplies = {}  # e.g. {-1001640903207: [100, 250, 3000]}

# fetch recent updates from telegram
def getTelegramUpdates():
    global lastUpdateID

    # offset by last updates retrieved
    url = "https://api.telegram.org/" + telegramAPIKey + "/getupdates?offset=" + str(lastUpdateID + 1)
    updates = requests.get(url)
    response = updates.json()["result"]

    if len(response):
        lastUpdateID = response[len(response) - 1]["update_id"]

    # logging.info(response)

    # check new messages
    for i in response:
        if "message" in i and "text" in i["message"]:
            checkForNewChatID(i["message"]["chat"]["id"])

            # respond to mentions with context
            if ("reply_to_message" in i["message"] and isSentence(i["message"]["text"]) and
                "username" in i["message"]["reply_to_message"]["from"] and
                i["message"]["reply_to_message"]["from"]["username"].startswith("Henrythe")):
                    triggerPrompt = i["message"]["from"]["username"] + ": " + i["message"]["text"] + "\n"

                    if "text" in i["message"]["reply_to_message"]:
                        triggerPrompt = "Henry the Hypemachine: " + i["message"]["reply_to_message"]["text"] + "\n" + i["message"]["from"]["username"] + ": " + i["message"]["text"] + "\n"

                    respondToMention(triggerPrompt, i["message"]["chat"]["id"], i["message"]["message_id"])

            # if an any-case match was found for one of henry's commands, and he hasn't already, respond
            for k in henryCommands:
                commandFound = False

                if "text" in i["message"] and anyCaseMatch(k, i["message"]["text"]):
                    commandFound = True

                if commandFound and i["message"]["message_id"] not in existingReplies[str(i["message"]["chat"]["id"])]:
                    sendResponse(i["message"]["chat"]["id"], i["message"]["message_id"], henryCommands[k])

            # if an any-case match was found for one of henry's triggers, and he hasn't already, respond
            for j in triggerMessages:
                triggerFound = False

                if "text" in i["message"] and anyCaseMatch(j, i["message"]["text"]):
                    triggerFound = True

                if triggerFound and isSentence(i["message"]["text"]) and i["message"]["message_id"] not in existingReplies[str(i["message"]["chat"]["id"])]:
                    triggerPrompt = ""

                    # if the matching message happens to be a reply itself, get thread context
                    if "reply_to_message" in i["message"]:
                        triggerPrompt = i["message"]["reply_to_message"]["from"]["username"] + ": " + i["message"]["reply_to_message"]["text"] + "\n" + i["message"]["from"]["username"] + ": " + i["message"]["text"] + "\n"
                    else:
                        triggerPrompt = i["message"]["from"]["username"] + ": " + i["message"]["text"]

                    triggerResponse(triggerPrompt, i["message"]["chat"]["id"], i["message"]["message_id"])

# fetch existing chats_ids from aws
def getExistingChatInformation():
    response = chatInfo.scan()

    for i in response["Items"]:
        if "last_reply" in i and i["last_reply"] is not None:
            existingChats[i["chat_id"]] = i["last_reply"]
        else:
            existingChats[i["chat_id"]] = ""

        existingReplies[str(i["chat_id"])] = ast.literal_eval(i["chat_replies"])

# save new chat information
def checkForNewChatID(chatID):
    if chatID not in existingChats:
        existingChats[chatID] = ""
        existingReplies[str(chatID)] = [0, 1]

        chatInfo.put_item(Item={"chat_id": chatID, "chat_replies": str([0, 1])})

# determine if chat is a group chat
def isGroupChat(chatID):
    type = "undetermined"

    try:
        url = "https://api.telegram.org/" + telegramAPIKey + "/getChat?chat_id=" + str(chatID)
        updates = requests.get(url)

        if "result" in updates.json() and "type" in updates.json()["result"] : type = updates.json()["result"]["type"]

        if type != "private": return True
        else: return False
    except requests.exceptions.HTTPError as err:
        logging.info("Henry was met with a closed door: " + err)

# determine if string is a sentence
def isSentence(s):
    return len(s.split()) > 1

# determine whether we're flooding a single chat or not
def isFloodingChat(chatID):
    if lastChatIDs[0] == chatID and lastChatIDs[1] == chatID and lastChatIDs[2] == chatID: return True
    else: return False

# determine if parse string has any-case match
def anyCaseMatch(match, parse):
    if match in parse or match.lower() in parse or match.upper() in parse: return True
    else: return False

# artificial seasoning
def spice(message, isReply, optionalPrompt):
    # construct message
    mess = "mess"
    r = random.randint(1, 10)

    # only reply 60% of the time Henry gets triggered
    if isReply == False and r > 6 and not anyCaseMatch("Henry", message):
        mess = ""

    if mess != "":
        # if no specific prompt was provided, choose a random one
        if optionalPrompt == "": optionalPrompt = defaultPrompt

        try:
            # season the prompt
            response = openai.Completion.create(
              model = "text-davinci-002",
              prompt = optionalPrompt + "\n\n'" + message + "'",
              temperature = 1.1,
              max_tokens = 60,
              top_p = 1,
              frequency_penalty = 0.9,
              presence_penalty = 0.9,
            )

            mess = response.choices[0].text.strip()

            # clean up the presentation
            mapping = [ ("Henry the Hypemachine:", ""), ("?\"", ""), ("ors", "ooors")]

            for k, v in mapping:
                mess = mess.replace(k, v)

            if mess[0] == '"' or mess[0] == "'": mess = mess[1:]
            if mess[-1] == '"' or mess[-1] == "'": mess = mess[:-1]
        except requests.exceptions.HTTPError as err:
            logging.info("Henry couldn't figure out how to open the door: " + err)

    return mess.strip()

# respond to direct mentions
def respondToMention(toMessage, chatID, messageID):
    cid = str(chatID)

    mess = spice(toMessage, True, "")

    if existingChats[chatID] != mess and mess != "":
        sendResponse(chatID, messageID, mess)

# trigger unique responses by keyword
def triggerResponse(toMessage, chatID, messageID):
    sendIt = True
    mess = ""

    # prevent flooding an individual chat in production
    if telegramAPIKey == os.getenv('PROD_TELEGRAM_API_KEY') and isFloodingChat(chatID):
        sendIt = False
    else:
        mess = spice(toMessage, False, "")

    # if the message was constructed and should be sent
    if existingChats[chatID] != mess and mess != "" and sendIt:
        sendResponse(chatID, messageID, mess)

# trigger random responses
def sendRandomMessage(shouldSend):
    chatID = random.choice(list(existingChats))
    mess = ""

    # prevent flooding an individual chat in production
    if telegramAPIKey == os.getenv('PROD_TELEGRAM_API_KEY') and isFloodingChat(chatID):
        shouldSend = False
    else:
        mess = spice(random.choice(randomMessages), False, "")

        while isGroupChat(chatID) != True and mess != "":
            chatID = random.choice(list(existingChats))

    # if the message was constructed and should be sent
    if existingChats[chatID] != mess and mess != "" and shouldSend:
        try:
            url = "https://api.telegram.org/" + telegramAPIKey + "/sendMessage?chat_id=" + str(chatID) + "&text=" + mess
            x = requests.post(url, json={})

            updateDatabase(chatID, existingReplies[str(chatID)], mess)

            lastChatIDs.pop(0)
            lastChatIDs.append(chatID)

            logging.info("Henry had some words to say in Chat " + str(chatID) + ": " + mess)
        except requests.exceptions.HTTPError as err:
            logging.info("Henry was met with a closed door: " + err)

# send henry's message(s) off to the telegram api
def sendResponse(chatID, messageID, message):
    cid = str(chatID)
    mid = str(messageID)

    try:
        existingChats[chatID] = message

        url = "https://api.telegram.org/" + telegramAPIKey + "/sendMessage?chat_id=" + cid + "&reply_to_message_id=" + mid + "&text=" + message
        x = requests.post(url, json={})

        # update local and database lists with new messageID
        replies = existingReplies[cid]
        replies.append(messageID)

        updateDatabase(chatID, replies, message)

        lastChatIDs.pop(0)
        lastChatIDs.append(chatID)

        time.sleep(2)

        logging.info("Henry had some words to say in Chat " + cid + ": " + message)

        # send a random BtB sticker 20% of the time
        r = random.randint(1, 10)

        if r < 3:
            stickerID = random.choice(list(stickerIDs))

            url = "https://api.telegram.org/" + telegramAPIKey + "/sendSticker?chat_id=" + str(chatID) + "&sticker=" + stickerID
            x = requests.post(url, json={})

            logging.info("Henry sent a sticker to Chat " + cid + ": " + stickerID)
    except requests.exceptions.HTTPError as err:
        logging.info("Henry was met with a closed door: " + err)

# update database
def updateDatabase(chatID, replies, lastReply):
    try:
        response = chatInfo.update_item(
            Key={
                "chat_id": chatID,
            },
            UpdateExpression="set #chat_replies=:r, #last_reply=:l",
            ExpressionAttributeNames={
                "#chat_replies": "chat_replies",
                "#last_reply": "last_reply",
            },
            ExpressionAttributeValues={
                ":r": str(replies),
                ":l": lastReply,
            },
            ReturnValues="UPDATED_NEW"
        )
    except requests.exceptions.HTTPError as err:
        logging.info("Henry was met with a closed door: " + err)

# initialize
if __name__ == "__main__":
    # get existing chat information and new updates off the rip
    getExistingChatInformation()
    getTelegramUpdates()

    chatCount = len(list(existingChats))
    runningTime, lastMessageTime, oneDaysTime = 0, 0, 86400
    waitTime, checkTime = 10, 15

    if chatCount < (oneDaysTime / 10):
        waitTime = oneDaysTime / chatCount

    # while running
    while True:
        if runningTime % round(waitTime, -1) == 0:
            sendRandomMessage(True)

        runningTime += checkTime
        time.sleep(checkTime)

        getExistingChatInformation()
        getTelegramUpdates()
