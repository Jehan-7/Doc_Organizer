import discord
from discord import app_commands
from discord.ext import commands,tasks
import sys
import pymongo
from pymongo import MongoClient
BOT_TOKEN = ''
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

YOUR_USER_ID = 123456789  # Replace with your user ID
message_list = {}
categories = {}
# Connect to MongoDB
client = MongoClient("")
print("Connected to MongoDB")  # Add this line
db = client["docorg"]

# Define MongoDB collections
message_collection = db["message_collection"]
category_collection = db["category_collection"]

# Function to update in-memory lists from MongoDB
async def update_lists_from_mongodb():
    # print("Updating lists from MongoDB...")  # Add this line
    global message_list, categories
    # Clear existing in-memory lists
    message_list = {}
    categories = {}
    try:
        # Retrieve data from MongoDB
        for message_info in message_collection.find():
            title = message_info["title"]
            category = message_info["category"]
            link = message_info["link"]

            message_list[title] = {"link": link, "category": category, "title": title}

            # Update categories
            if category not in categories:
                categories[category] = []
            categories[category].append(title)

        # print("In-memory lists updated from MongoDB.")
        await send_updated_list()  # Use 'await' when calling the asynchronous function
    except Exception as e:
        print(f"An error occurred during update_lists_from_mongodb: {e}")

# Define the loop for periodic updates
@tasks.loop(minutes=2)  # Adjust the interval as needed
async def update_lists():
    await update_lists_from_mongodb()
@bot.tree.command(name="update")
@app_commands.describe()
async def force_update(interaction: discord.Interaction):
    """
    Force an immediate update from the MongoDB database.
    """
    try:
        await interaction.response.defer(ephemeral=True)
        print("Forced update from MongoDB...")  # Add this line
        global message_list, categories
        # Clear existing in-memory lists
        message_list = {}
        categories = {}
        # Retrieve data from MongoDB
        for message_info in message_collection.find():
            title = message_info["title"]
            category = message_info["category"]
            link = message_info["link"]

            message_list[title] = {"link": link, "category": category, "title": title}

            # Update categories
            if category not in categories:
                categories[category] = []
            categories[category].append(title)

        print("In-memory lists updated from MongoDB.")
        await send_updated_list()  # Use 'await' when calling the asynchronous function
        await interaction.followup.send("Forced update from the database completed.")
    except Exception as e:
        print(f"An error occurred during the force_update: {e}")
        await interaction.followup.send(f"An error occurred during the force_update: {e}")

@bot.event
async def on_ready():
    print("Bot is Up and Ready!")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
        update_lists.start()
    except Exception as e:
        print(e)

@bot.tree.command(name="append")
@app_commands.describe(title="Name of the Literary work/The title of the message", category="Category to append to", link="Link to the message")
async def appending(interaction: discord.Interaction, title: str, category: str, link: str):
    """
    Append a message link to the list with a given label and category.

    Example usage: !append ABCD General https://discord.com/channels/123456789012345678/123456789012345678/123456789012345678
    """
    # Check if the link is a valid Discord message link
    if "https://discord.com/channels/" not in link:
        await interaction.response.send_message("Error: Invalid Discord message link.")
        return

    # Convert category and title to lowercase for case-insensitive comparison
    category_lower = category.lower()
    title_lower = title.lower()

    # Check if the title already exists in any category
    if title_lower in (key.lower() for key in message_list):
        await interaction.response.send_message(f"Error: Entry with the same title already exists across categories.")
        return

    # Check if the title already exists in the specified category
    if category_lower in categories and title_lower in categories[category_lower]:
        await interaction.response.send_message(f"Error: Entry with the same title already exists in the category '{category}'.")
        return

    # Check if the category exists, if not, inform the user
    if category_lower not in categories:
        await interaction.response.send_message(f"Error: Category '{category}' doesn't exist. You can add it using /add_category.")
        return

    # Append to the in-memory list and the category
    message_list[title] = {"link": link, "category": category_lower, "title": title_lower}
    categories[category_lower].append(title_lower)

    # Insert into MongoDB
    message_collection.insert_one({"title": title_lower, "category": category_lower, "link": link})
    category_collection.update_one({"category": category_lower}, {"$push": {"entries": title_lower}}, upsert=True)

    await interaction.response.send_message(f"Message appended with label '{title}' to category '{category}'.")
    # await send_updated_list()

@bot.tree.command(name="mass_append")
async def mass_append(interaction: discord.Interaction, archives: str):
    import re
    try:
        await interaction.response.defer(ephemeral=True)  # defer
        # Clear existing entries in MongoDB
        message_collection.delete_many({})
        category_collection.delete_many({})
        # Split input into categories and entries
        parts = re.split(r"\s*\*\*(.*?)\*\*=\s*", archives)[1:]  # Use regex to split by category name

        for i in range(0, len(parts), 2):
            # Extract category and entries
            current_category = parts[i]
            entries_text = parts[i + 1]

            # Extract entries
            entry_matches = re.findall(r"\[.*?\]\((.*?)\)", entries_text)
            texts=re.findall(r"\[([^\]]+)\]", entries_text)
            j=0
            for link in entry_matches:
                if any(entry["link"] == link for entry in message_list.values()):
                    await interaction.response.send_message(f"Error: Entry with the same link already exists for '{link}'. Skipping.")
                    continue
                
                # Check if the category exists, if not, create it
                category_lower = current_category.lower()
                if category_lower not in categories:
                    categories[category_lower] = []

                # Generate a title based on the link
                title = texts[j]
                j=j+1
            
                # Append to the message list and the category
                message_list[title] = {"link": link, "category": category_lower, "title": title}
                categories[category_lower].append(title)
        # Calculate memory usage of message_list and categories
        message_list_size = sys.getsizeof(message_list)
        categories_size = sys.getsizeof(categories)
        # Insert the updated list into MongoDB
        for title, message_info in message_list.items():
            message_collection.insert_one(message_info)

        for category, entries in categories.items():
            category_collection.insert_one({"category": category, "entries": entries})

        print(f"Memory usage of message_list: {message_list_size} bytes")
        print(f"Memory usage of categories: {categories_size} bytes")
            
        # await interaction.response.send_message("Archives mass-appended successfully:\n")
        await interaction.followup.send("Archives mass-appended successfully:\n")
        await send_updated_list()
    except Exception as e:
        print(f"An error occurred during mass_append: {e}")
        # await interaction.response.send_message(f"An error occurred during mass_append: {e}")
        await interaction.followup.send(f"An error occurred during mass_append: {e}")

@bot.tree.command(name="add_category")
@app_commands.describe(category="Name of the category to add")
async def add_category(interaction: discord.Interaction, category: str):
    """
    Add a new category.

    Example usage: !add_category General
    """
    # Check if the category already exists
    category = category.lower()
    if category in categories:
        await interaction.response.send_message(f"Error: Category '{category}' already exists.")
        return

    # Add the new category
    categories[category] = []
    await interaction.response.send_message(f"Category '{category}' added successfully.")
    # await send_updated_list()

@bot.tree.command(name="lis_archives")
@app_commands.describe(category="Category to display (use 'all' for all categories)")
async def list_labels(interaction: discord.Interaction, category: str):
    """
    List all labels and their corresponding message links by category.
    """
    await interaction.response.defer()  # defer

    if not categories:
        await interaction.followup.send("No archives found.")
        return

    try:
        # Create a formatted list of labels by category
        if category.lower() == "all":
            content = ""
            for cat, labels in categories.items():
                label_list = "\n".join([f"[{label}]( {message_list[label]['link']} )\n" for label in labels])
                content += f"**{cat}**:\n{label_list}\n\n"
        else:
            category = category.lower()
            if category not in categories:
                await interaction.followup.send(f"No entries found for category '{category}'.")
                return

            content = ""
            label_list = "\n".join([f"[{label}]( {message_list[label]['link']} )\n" for label in categories[category]])
            content += f"**{category}**:\n{label_list}"

        # Split the content into chunks
        for chunk in chunks(content, max_length=2000):
            await interaction.followup.send(chunk)

    except discord.errors.NotFound:
        # Handle case where interaction is not found
        pass

# Helper function to split content into chunks without breaking entries
def chunks(content, max_length):
    chunks = []
    current_chunk = ""
    
    for line in content.split('\n'):
        if len(current_chunk) + len(line) < max_length:
            current_chunk += line + '\n'
        else:
            chunks.append(current_chunk.strip())
            current_chunk = line + '\n'

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks


@bot.tree.command(name="lis_categories")
async def list_categories(interaction: discord.Interaction):
    """
    List all categories.
    """
    if not categories:
        await interaction.response.send_message("No categories found.")
        return

    category_list = "\n".join(categories.keys())
    await interaction.response.send_message(f"List of Categories:\n{category_list}")

@bot.tree.command(name="delete_archive")
@app_commands.describe(title="Name of the Literary work/The title of the message")
async def delete_entry(interaction: discord.Interaction, title: str):
    """
    Delete an entry from the list based on the provided title.

    Example usage: !delete_archive ABCD
    """
    # Convert the title to lowercase for case-insensitive comparison
    title_lower = title.lower()

    # Check if the title is in the message_list
    if title_lower in (key.lower() for key in message_list):
        # Find the original case of the title
        original_title = next(key for key in message_list if key.lower() == title_lower)

        # Delete the entry from MongoDB
        message_collection.delete_one({"title": original_title})

        # Delete the entry from the category
        category = message_list[original_title]["category"]
        categories[category].remove(original_title)

        # Delete the entry from the category_collection
        category_collection.update_one({"category": category}, {"$pull": {"entries": original_title}})

        # Delete the entry from the message_list
        del message_list[original_title]

        await interaction.response.send_message(f"Entry with label '{original_title}' deleted.")
        await send_updated_list()
    else:
        await interaction.response.send_message(f"Error: Entry with label '{title}' not found.")

@bot.tree.command(name="delete_category")
@app_commands.describe(category="Name of the category to delete")
async def delete_category(interaction: discord.Interaction, category: str):
    """
    Delete a category and all archives within that category.

    Example usage: !delete_category General
    """
    await interaction.response.defer()  # defer

    # Convert the category to lowercase for case-insensitive comparison
    category_lower = category.lower()

    # Check if the category exists
    if category_lower not in categories:
        await interaction.followup.send(f"Error: Category '{category_lower}' not found.")
        return

    # Delete each entry in the category from MongoDB
    for title in categories[category_lower]:
        message_collection.delete_one({"title": title})

    # Delete each entry in the category from the message_list
    for title in categories[category_lower]:
        del message_list[title]

    # Delete the category from MongoDB
    category_collection.delete_one({"category": category_lower})

    # Delete the category from the in-memory list
    del categories[category_lower]

    # await interaction.response.send_message(f"Category '{category_lower}' and all its archives deleted.")
    await interaction.followup.send(f"Category '{category_lower}' and all its archives deleted.")

    # await send_updated_list()

@bot.tree.command(name="help")
async def help_command(interaction: discord.Interaction):
    """
    List the available commands and provide information about the bot.
    """
    # await interaction.response.defer(ephemeral=True)  # defer
    info_message = (
        "Welcome to Doc_Organizer! 📚✨\n\n"
        "🗃🗄 **About Doc_Organizer:**\n"
        "Doc_Organizer is designed to help you efficiently organize and categorize literary works or messages within your server. With it, you can keep track of important messages and literary pieces with ease.📂\n\n"
        "🔄 **Automatic Updates:**\n"
        "Doc_Organizer automatically updates its information from the database every 2 hours, ensuring that your data is always up-to-date.\n\n"
        "🌟 **Key Commands:**\n"
        "- `/add_category`: Add a new category to organize your archives.\n"
        "- `/append`: Append a message link to the list with a given label and category.\n"
        "- `/lis_archives`: Display the list of stored messages organized by category. **Note: Avoid using 'all' as it may result in a large list.**\n"
        "- `/lis_categories`: View the list of existing categories.\n"
        "- `/delete_archive`: Delete a specific archive based on the provided title.\n"
        "- `/delete_category`: Delete an entire category and all its archives.\n"
        "- **`/update`: Force an immediate update from the last scheduled update.**\n"
        "- **`/mass_append`: Use only if the bot has been offline for a while. Recommended to not use it.**\n"
        "- `/help`: Display information about the bot and commands.\n\n"
        "🚫 **Do-Nots:**\n"
        "1. **Use the `/mass_append` command judiciously, as it can lead to a large number of entries and may affect performance.**\n"
        "2. **Do not delete categories without consideration:** Deleting a category removes all archives within that category; be cautious when using `/delete_category`.\n"
        "3. **Avoid using special characters in titles:** Stick to alphanumeric characters (0-9 and a-z).\n\n"
        "🔍 **Additional Features:**\n"
        "- **Message Previews:** Hover over message links in the list to see a preview of the content.\n"
        "📌 **Note:** The bot is still in development, and you might encounter some bugs. Please report them to me. 🗂️\n"
        "🌐 **External Links:** Ensure that message links are from your server for accurate categorization."
    )
    # await interaction.followup.send(info_message)
    await interaction.response.send_message(info_message)
    
async def send_updated_list():
    guild_id = 1234567890 # Replace YOUR_GUILD_ID with the actual guild ID
    channel_id = 1234567890  # Replace YOUR_CHANNEL_ID with the actual channel ID

    guild = bot.get_guild(guild_id)
    channel = guild.get_channel(channel_id)

    if channel:
        # Collect the last 30 records across all categories
        all_records = [label for labels in categories.values() for label in labels]
        last_30_records = all_records[-30:]

        if last_30_records:
            # Split the records into chunks of 10 for each message
            chunk_size = 10
            chunks = [last_30_records[i:i + chunk_size] for i in range(0, len(last_30_records), chunk_size)]

            # Send updates to the specified channel
            for chunk in chunks:
                chunk_content = "\n".join([f"[{label}]( {message_list[label]['link']} )\n" for label in chunk])
                await channel.send(f"Here are the latest updates:\n\n{chunk_content}")
        else:
            await channel.send("No categories or labels to display.")


# Keep the bot running and scheduling
bot.run(BOT_TOKEN)