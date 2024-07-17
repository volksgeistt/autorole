import discord
from discord.ext import commands
import json
from typing import Dict, List, Tuple, Any
from collections import defaultdict
from functools import wraps
import uuid

class RoleLimit(Exception):
    pass

def role_limit_decorator(func):
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except RoleLimit as e:
            interaction = next((arg for arg in args if isinstance(arg, discord.Interaction)), None)
            if interaction:
                await interaction.response.send_message(str(e), ephemeral=True)
    return wrapper

class AutoRoleManager:
    def __init__(self):
        self.data: Dict[str, Dict[str, List[int]]] = defaultdict(lambda: {"humans": [], "bots": []})
        
    def delete_template(self, guild_id: str, template_id: str) -> bool:
        try:
            with open('db/autorole_templates.json', 'r') as f:
                templates = json.load(f)
        except FileNotFoundError:
            return False
        if guild_id not in templates or template_id not in templates[guild_id]:
            return False
        del templates[guild_id][template_id]
        with open('db/autorole_templates.json', 'w') as f:
            json.dump(templates, f, indent=4)
        return True

    def save_template(self, guild_id: str, template_name: str) -> str:
        template_id = str(uuid.uuid4())
        template = {
            "name": template_name,
            "humans": self.data[guild_id]["humans"],
            "bots": self.data[guild_id]["bots"]
        }
        try:
            with open('db/autorole_templates.json', 'r') as f:
                templates = json.load(f)
        except FileNotFoundError:
            templates = {}
        if guild_id not in templates:
            templates[guild_id] = {}
        if len(templates[guild_id]) >= 10:
            return None
        templates[guild_id][template_id] = template
        with open('db/autorole_templates.json', 'w') as f:
            json.dump(templates, f, indent=4)
        return template_id

    def load_template(self, guild_id: str, template_id: str) -> bool:
        try:
            with open('db/autorole_templates.json', 'r') as f:
                templates = json.load(f)
        except FileNotFoundError:
            return False
        
        if guild_id not in templates or template_id not in templates[guild_id]:
            return False
        
        template = templates[guild_id][template_id]
        self.data[guild_id]["humans"] = template["humans"]
        self.data[guild_id]["bots"] = template["bots"]
        self.save_data()
        return True

    def list_templates(self, guild_id: str) -> List[Dict[str, Any]]:
        try:
            with open('db/autorole_templates.json', 'r') as f:
                templates = json.load(f)
        except FileNotFoundError:
            return []
        
        if guild_id not in templates:
            return []
        
        return [{"id": id, "name": template["name"], "humans": template["humans"], "bots": template["bots"]} 
                for id, template in templates[guild_id].items()]

    def load_data(self):
        try:
            with open('db/autorole.json', 'r') as f:
                self.data = defaultdict(lambda: {"humans": [], "bots": []}, json.load(f))
        except FileNotFoundError:
            pass

    def save_data(self):
        with open('db/autorole.json', 'w') as f:
            json.dump(dict(self.data), f, indent=4)

    def check_role_limit(self, guild_id: str, role_type: str) -> Tuple[bool, int]:
        current_roles = self.data[guild_id][role_type]
        max_roles = 5 if role_type == "humans" else 2
        return len(current_roles) >= max_roles, max_roles

    def add_role(self, guild_id: str, role_type: str, role_id: int) -> None:
        at_limit, max_roles = self.check_role_limit(guild_id, role_type)
        if at_limit:
            raise RoleLimit(f"Maximum limit of {max_roles} roles for {role_type} has been reached.")
        if role_id not in self.data[guild_id][role_type]:
            self.data[guild_id][role_type].append(role_id)
            self.save_data()

    def remove_role(self, guild_id: str, role_type: str, role_id: int) -> None:
        if role_id in self.data[guild_id][role_type]:
            self.data[guild_id][role_type].remove(role_id)
            self.save_data()

    def get_roles(self, guild_id: str, role_type: str) -> List[int]:
        return self.data[guild_id][role_type]

    def reset_guild(self, guild_id: str) -> None:
        if guild_id in self.data:
            del self.data[guild_id]
            self.save_data()

class AutoRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.manager = AutoRoleManager()
        self.manager.load_data()

    @commands.command(name="setup")
    @commands.has_permissions(manage_roles=True)
    async def autorole(self, ctx):
        embed = discord.Embed(description=">>> Navigate through the buttons below to setup and configure **Autorole Module** into the guild and start assigning roles to members.\n- **Human Autoroles Limit:** `5`\n- **Bot Autoroles Limit:** `2`", color=discord.Color.blurple())
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=self.bot.user.avatar)
        embed.set_author(name=f"Autorole Setup Menu", icon_url=self.bot.user.avatar)
        view = AutoroleView(self.bot, self.manager, ctx.author.id, ctx.guild.id)
        message = await ctx.send(embed=embed, view=view)
        await view.wait()
        if view.value is None:
            error_embed = discord.Embed(description="**Autorole Setup Menu** has been timed out.", color=discord.Color.blurple())
            await message.edit(embed=error_embed, view=None)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild_id = str(member.guild.id)
        role_type = "bots" if member.bot else "humans"
        roles = self.manager.get_roles(guild_id, role_type)
        for role_id in roles:
            role = member.guild.get_role(role_id)
            if role:
                try:
                    await member.add_roles(role, reason=f"{self.bot.user.name} @ {role_type} autorole")
                except discord.HTTPException:
                    pass

class AutoroleView(discord.ui.View):
    def __init__(self, bot, manager: AutoRoleManager, user_id: int, guild_id: int):
        super().__init__(timeout=300)
        self.bot = bot
        self.manager = manager
        self.user_id = user_id
        self.guild_id = guild_id
        self.value = None

    @discord.ui.button(label="Setup Human Autoroles", style=discord.ButtonStyle.primary)
    @role_limit_decorator
    async def humans(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("**This interaction menu is not yours.**", ephemeral=True)
            return
        await self.setup_roles(interaction, "humans")

    @discord.ui.button(label="Setup Bot Autoroles", style=discord.ButtonStyle.secondary)
    @role_limit_decorator
    async def bots(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("**This interaction menu is not yours.**", ephemeral=True)
            return
        await self.setup_roles(interaction, "bots")

    @discord.ui.button(label="Config Autoroles", style=discord.ButtonStyle.success)
    async def config(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("**This interaction menu is not yours.**", ephemeral=True)
            return
        
        guild_id = str(self.guild_id)
        human_roles = self.manager.get_roles(guild_id, "humans")
        bot_roles = self.manager.get_roles(guild_id, "bots")
        
        human_role_mentions = ", ".join([f"<@&{role_id}>" for role_id in human_roles]) or "Not Configured Yet"
        bot_role_mentions = ", ".join([f"<@&{role_id}>" for role_id in bot_roles]) or "Not Configured Yet"
        
        embed = discord.Embed(color=discord.Color.blurple())
        embed.set_author(name=f"Autorole Setup Config", icon_url=interaction.user.avatar.url)
        embed.set_footer(icon_url=interaction.user.avatar.url, text=f"Requested by {interaction.user.name}")
        embed.add_field(name="Human Autoroles", value=human_role_mentions, inline=False)
        embed.add_field(name="Bot Autoroles", value=bot_role_mentions, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Reset Autoroles", style=discord.ButtonStyle.danger)
    async def reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("**This interaction menu is not yours.**", ephemeral=True)
            return
        self.manager.reset_guild(str(self.guild_id))
        embed = discord.Embed(description=f"All the roles and setup data for autoroles including **Humans** and **Bots** have been cleared and no roles will be assigned to the users upon joining!", color=discord.Color.blurple())
        embed.set_author(name="Autorole Setup Cleared", icon_url=interaction.user.avatar.url)
        embed.set_footer(text=f"Action performed by {interaction.user.name}", icon_url=interaction.user.avatar.url)
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="List Autorole Templates", style=discord.ButtonStyle.grey)
    async def list_templates(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("**This interaction menu is not yours.**", ephemeral=True)
            return
        
        templates = self.manager.list_templates(str(self.guild_id))
        if not templates:
            await interaction.response.send_message("No templates found for this guild.", ephemeral=True)
            return

        paginator = TemplatesPaginator(self.bot, templates)
        await interaction.response.send_message(embed=paginator.get_current_embed(), view=paginator, ephemeral=True)

    async def setup_roles(self, interaction: discord.Interaction, role_type: str):
        guild = interaction.guild
        roles = [role for role in guild.roles if role < guild.me.top_role and not role.managed and role != guild.default_role]
        
        at_limit, max_roles = self.manager.check_role_limit(str(self.guild_id), role_type)
        if at_limit:
            raise RoleLimit(f"Maximum limit of {max_roles} roles for {role_type} has been reached.")
        
        view = RoleSelectView(self.manager, self.user_id, roles, role_type, str(self.guild_id))
        await interaction.response.send_message(f"**Select roles for {role_type} autorole! ( Max Limit: {max_roles})**", view=view, ephemeral=True)
        
        await view.wait()
        if not view.roles:
            await interaction.followup.send(f"oops! this **Autorole** setup menu has timed out due to inactivity!")
            return

        role_mentions = ", ".join([role.mention for role in view.roles])
        embed = discord.Embed(description=f"Alright! **{role_type}** autorole has been setup and roles will be assigned to users upon joining from now onwards!", color=discord.Color.blurple())
        embed.add_field(name=f"**__Roles__**", value=role_mentions)
        embed.set_footer(icon_url=interaction.user.avatar.url, text=f"Action performed by {interaction.user.name}")
        embed.set_author(name=f"Autorole Setup", icon_url=interaction.user.avatar.url)
        await interaction.followup.send(embed=embed)

    @discord.ui.button(label="Save Autorole Template", style=discord.ButtonStyle.grey)
    async def save_template(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("**This interaction menu is not yours.**", ephemeral=True)
            return
        
        await interaction.response.send_modal(SaveTemplateModal(self.manager, self.guild_id))

    @discord.ui.button(label="Load Autorole Template", style=discord.ButtonStyle.grey)
    async def load_template(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("**This interaction menu is not yours.**", ephemeral=True)
            return
        
        templates = self.manager.list_templates(str(self.guild_id))
        if not templates:
            await interaction.response.send_message("No templates found for this guild.", ephemeral=True)
            return
        
        view = LoadTemplateView(self.manager, self.guild_id, templates)
        await interaction.response.send_message("Select a template to load:", view=view, ephemeral=True)

    @discord.ui.button(label="Delete Template", style=discord.ButtonStyle.danger)
    async def delete_template(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("**This interaction menu is not yours.**", ephemeral=True)
            return
        
        templates = self.manager.list_templates(str(self.guild_id))
        if not templates:
            await interaction.response.send_message("No templates found for this guild.", ephemeral=True)
            return
        
        view = DeleteTemplateView(self.manager, str(self.guild_id), templates)
        await interaction.response.send_message("Select a template to delete:", view=view, ephemeral=True)

class SaveTemplateModal(discord.ui.Modal, title="Save Autorole Template"):
    template_name = discord.ui.TextInput(label="Template Name", placeholder="Enter a name for your template")

    def __init__(self, manager: AutoRoleManager, guild_id: int):
        super().__init__()
        self.manager = manager
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        template_id = self.manager.save_template(str(self.guild_id), self.template_name.value)
        if template_id is None:
            await interaction.response.send_message("Maximum limit of 10 templates reached. Please delete an existing template before saving a new one.", ephemeral=True)
        else:
            embed = discord.Embed(
                description=f"Template **{self.template_name.value}** has been saved.\nTemplate ID: `{template_id}`",
                color=discord.Color.blurple()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

class LoadTemplateView(discord.ui.View):
    def __init__(self, manager: AutoRoleManager, guild_id: int, templates: List[Dict[str, Any]]):
        super().__init__()
        self.manager = manager
        self.guild_id = guild_id
        self.add_item(LoadTemplateSelect(manager, guild_id, templates))

class LoadTemplateSelect(discord.ui.Select):
    def __init__(self, manager: AutoRoleManager, guild_id: int, templates: List[Dict[str, Any]]):
        self.manager = manager
        self.guild_id = guild_id
        options = [discord.SelectOption(label=template["name"], value=template["id"]) for template in templates]
        super().__init__(placeholder="Select a template to load", options=options)

    async def callback(self, interaction: discord.Interaction):
        success = self.manager.load_template(str(self.guild_id), self.values[0])
        if success:
            embed = discord.Embed(
                description="The template has been successfully loaded and applied to this server.",
                color=discord.Color.blurple()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("Failed to load the template. Please try again.", ephemeral=True)

class DeleteTemplateView(discord.ui.View):
    def __init__(self, manager: AutoRoleManager, guild_id: str, templates: List[Dict[str, Any]]):
        super().__init__()
        self.manager = manager
        self.guild_id = guild_id
        self.add_item(DeleteTemplateSelect(manager, guild_id, templates))

class DeleteTemplateSelect(discord.ui.Select):
    def __init__(self, manager: AutoRoleManager, guild_id: str, templates: List[Dict[str, Any]]):
        self.manager = manager
        self.guild_id = guild_id
        options = [discord.SelectOption(label=template["name"], value=template["id"]) for template in templates]
        super().__init__(placeholder="Select a template to delete", options=options)

    async def callback(self, interaction: discord.Interaction):
        success = self.manager.delete_template(self.guild_id, self.values[0])
        if success:
            embed = discord.Embed(
                description=f"The template has been successfully deleted.",
                color=discord.Color.blurple()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("Failed to delete the template. Please try again.", ephemeral=True)

class TemplatesPaginator(discord.ui.View):
    def __init__(self, bot, templates: List[Dict[str, Any]]):
        super().__init__(timeout=300)
        self.bot = bot
        self.templates = templates
        self.current_page = 0

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.gray)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = (self.current_page - 1) % len(self.templates)
        await interaction.response.edit_message(embed=self.get_current_embed(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.gray)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = (self.current_page + 1) % len(self.templates)
        await interaction.response.edit_message(embed=self.get_current_embed(), view=self)

    def get_current_embed(self) -> discord.Embed:
        template = self.templates[self.current_page]
        embed = discord.Embed(title=f"Template Name: {template['name']}", color=discord.Color.blurple())
        embed.add_field(name="📝 Template ID", value=f"`{template['id']}`", inline=False)
        
        human_roles = ", ".join([f"<@&{role_id}>" for role_id in template['humans']]) or "None"
        bot_roles = ", ".join([f"<@&{role_id}>" for role_id in template['bots']]) or "None"
        
        embed.add_field(name="🧔🏻‍♂️ Human Roles", value=human_roles, inline=False)
        embed.add_field(name="🤖 Bot Roles", value=bot_roles, inline=False)
        embed.set_footer(text=f"Page {self.current_page + 1}/{len(self.templates)}", icon_url=self.bot.user.avatar)
        return embed

class RoleSelectView(discord.ui.View):
    def __init__(self, manager: AutoRoleManager, user_id: int, roles: List[discord.Role], role_type: str, guild_id: str):
        super().__init__(timeout=300)
        self.manager = manager
        self.user_id = user_id
        self.roles: List[discord.Role] = []
        self.role_type = role_type
        self.guild_id = guild_id
        self.add_item(RoleSelect(roles, role_type, manager.check_role_limit(guild_id, role_type)[1]))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

class RoleSelect(discord.ui.Select):
    def __init__(self, roles: List[discord.Role], role_type: str, max_roles: int):
        options = [discord.SelectOption(label=role.name, value=str(role.id)) for role in roles[:25]]
        super().__init__(placeholder=f"Select roles", options=options, max_values=max_roles)

    async def callback(self, interaction: discord.Interaction):
        view: RoleSelectView = self.view
        selected_roles = [interaction.guild.get_role(int(value)) for value in self.values]
        
        for role in selected_roles:
            try:
                view.manager.add_role(view.guild_id, view.role_type, role.id)
                view.roles.append(role)
            except RoleLimit as e:
                await interaction.response.send_message(str(e), ephemeral=True)
                return
        await interaction.response.defer()
        view.stop()

async def setup(bot):
    await bot.add_cog(AutoRole(bot))
