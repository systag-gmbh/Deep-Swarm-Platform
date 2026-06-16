#!/usr/bin/env -S dotnet run
#:project lib/StackLib.csproj
#:package BCrypt.Net-Next@4.0.3
#:package Newtonsoft.Json@13.0.4

using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using StackLib;

var repoRoot = Environment.CurrentDirectory;
var usersFile = Path.Combine(repoRoot, "services", "90-caddy", "users.json");
var usersExample = Path.Combine(repoRoot, "services", "90-caddy", "users.json.example");

if (args.Length == 0)
{
    ShowHelp();
    return;
}

var command = args[0].ToLower();

switch (command)
{
    case "add":
        AddUser();
        break;
    case "list":
        ListUsers();
        break;
    case "hash":
        HashPassword();
        break;
    case "init":
        InitUsers();
        break;
    case "delete":
        DeleteUser();
        break;
    case "update":
        UpdateUser();
        break;
    default:
        Console.WriteLine($"Unknown command: {command}");
        ShowHelp();
        break;
}

void ShowHelp()
{
    Console.WriteLine("Caddy Security User Management");
    Console.WriteLine();
    Console.WriteLine("Usage: dotnet run scripts/caddy-users.cs <command>");
    Console.WriteLine();
    Console.WriteLine("Commands:");
    Console.WriteLine("  init              Create users.json from template");
    Console.WriteLine("  add               Add a new user interactively");
    Console.WriteLine("  update            Update an existing user");
    Console.WriteLine("  delete            Delete a user by username");
    Console.WriteLine("  list              List all users");
    Console.WriteLine("  hash              Generate a bcrypt hash for a password");
    Console.WriteLine();
    Console.WriteLine("Examples:");
    Console.WriteLine("  dotnet run scripts/caddy-users.cs init");
    Console.WriteLine("  dotnet run scripts/caddy-users.cs add");
    Console.WriteLine("  dotnet run scripts/caddy-users.cs update");
    Console.WriteLine("  dotnet run scripts/caddy-users.cs delete");
    Console.WriteLine("  dotnet run scripts/caddy-users.cs list");
    Console.WriteLine("  dotnet run scripts/caddy-users.cs hash");
}

void InitUsers()
{
    if (File.Exists(usersFile))
    {
        Console.WriteLine($"users.json already exists at: {usersFile}");
        Console.Write("Overwrite? (y/N): ");
        var response = Console.ReadLine()?.Trim().ToLower();
        if (response != "y")
        {
            Console.WriteLine("Aborted.");
            return;
        }
    }

    File.Copy(usersExample, usersFile, overwrite: true);
    Console.WriteLine($"Created users.json from template.");
    Console.WriteLine($"Location: {usersFile}");
    Console.WriteLine();
    Console.WriteLine("Next steps:");
    Console.WriteLine("  1. Run: dotnet run scripts/caddy-users.cs add");
    Console.WriteLine("  2. Rebuild Caddy: docker compose -f services/90-caddy/docker-compose.yml build");
    Console.WriteLine("  3. Restart stack: dotnet run scripts/start.cs");
}

void AddUser()
{
    var db = LoadOrCreateDatabase();

    Console.Write("Username: ");
    var username = Console.ReadLine()?.Trim() ?? "";
    if (string.IsNullOrEmpty(username))
    {
        Console.WriteLine("Username is required.");
        return;
    }

    // Check if user already exists
    var users = (JArray)db["users"]!;
    if (users.Any(u => u["username"]?.ToString() == username))
    {
        Console.WriteLine($"User '{username}' already exists.");
        return;
    }

    Console.Write("Email: ");
    var email = Console.ReadLine()?.Trim() ?? "";
    if (string.IsNullOrEmpty(email))
    {
        Console.WriteLine("Email is required.");
        return;
    }

    Console.Write("Password: ");
    var password = ReadPassword();
    Console.WriteLine();

    if (string.IsNullOrEmpty(password))
    {
        Console.WriteLine("Password is required.");
        return;
    }

    Console.Write("Confirm password: ");
    var confirmPassword = ReadPassword();
    Console.WriteLine();

    if (password != confirmPassword)
    {
        Console.WriteLine("Passwords do not match.");
        return;
    }

    Console.Write("Role (admin/user) [user]: ");
    var roleInput = Console.ReadLine()?.Trim().ToLower() ?? "user";
    var role = roleInput == "admin" ? "authp/admin" : "authp/user";

    // Generate password hash
    var hash = BCrypt.Net.BCrypt.HashPassword(password, 10);

    // Extract domain from email
    var domain = email.Contains('@') ? email.Split('@')[1] : "example.com";

    // Create user object
    var now = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
    var user = new JObject
    {
        ["id"] = Guid.NewGuid().ToString(),
        ["username"] = username,
        ["email_addresses"] = new JArray
        {
            new JObject
            {
                ["address"] = email,
                ["domain"] = domain
            }
        },
        ["passwords"] = new JArray
        {
            new JObject
            {
                ["purpose"] = "generic",
                ["algorithm"] = "bcrypt",
                ["hash"] = hash,
                ["cost"] = 10,
                ["expired_at"] = "0001-01-01T00:00:00Z",
                ["created_at"] = now,
                ["disabled_at"] = "0001-01-01T00:00:00Z"
            }
        },
        ["created"] = now,
        ["last_modified"] = now,
        ["roles"] = new JArray
        {
            new JObject
            {
                ["name"] = role,
                ["organization"] = "authp"
            }
        }
    };

    users.Add(user);
    db["revision"] = (int)db["revision"]! + 1;

    SaveDatabase(db);
    Console.WriteLine($"User '{username}' added successfully with role '{role}'.");
    RestartCaddyIfRunning();
}

void DeleteUser()
{
    if (!File.Exists(usersFile))
    {
        Console.WriteLine("No users.json found. Run 'init' first.");
        return;
    }

    Console.Write("Username to delete: ");
    var username = Console.ReadLine()?.Trim() ?? "";
    if (string.IsNullOrEmpty(username))
    {
        Console.WriteLine("Username is required.");
        return;
    }

    var db = LoadDatabase();
    var users = (JArray)db["users"]!;

    var userToken = users.FirstOrDefault(u => u["username"]?.ToString() == username);
    if (userToken == null)
    {
        Console.WriteLine($"User '{username}' not found.");
        return;
    }

    Console.Write($"Are you sure you want to delete user '{username}'? (y/N): ");
    var response = Console.ReadLine()?.Trim().ToLower();
    if (response != "y")
    {
        Console.WriteLine("Aborted.");
        return;
    }

    users.Remove(userToken);
    db["revision"] = (int)db["revision"]! + 1;

    SaveDatabase(db);
    Console.WriteLine($"User '{username}' deleted successfully.");
    RestartCaddyIfRunning();
}

void UpdateUser()
{
    if (!File.Exists(usersFile))
    {
        Console.WriteLine("No users.json found. Run 'init' first.");
        return;
    }

    Console.Write("Username to update: ");
    var username = Console.ReadLine()?.Trim() ?? "";
    if (string.IsNullOrEmpty(username))
    {
        Console.WriteLine("Username is required.");
        return;
    }

    var db = LoadDatabase();
    var users = (JArray)db["users"]!;

    var userToken = users.FirstOrDefault(u => u["username"]?.ToString() == username);
    if (userToken == null)
    {
        Console.WriteLine($"User '{username}' not found.");
        return;
    }

    var user = (JObject)userToken;
    var currentEmail = user["email_addresses"]?[0]?["address"]?.ToString() ?? "";
    var currentRole = user["roles"]?[0]?["name"]?.ToString() ?? "";
    var displayRole = currentRole == "authp/admin" ? "admin" : "user";

    Console.WriteLine($"Current email: {currentEmail}");
    Console.WriteLine($"Current role: {displayRole}");
    Console.WriteLine();
    Console.WriteLine("Press Enter to keep current value.");
    Console.WriteLine();

    Console.Write($"New email [{currentEmail}]: ");
    var newEmail = Console.ReadLine()?.Trim() ?? "";

    Console.Write("New password (leave blank to keep current): ");
    var newPassword = ReadPassword();
    Console.WriteLine();

    string? confirmedPassword = null;
    if (!string.IsNullOrEmpty(newPassword))
    {
        Console.Write("Confirm new password: ");
        var confirmPassword = ReadPassword();
        Console.WriteLine();

        if (newPassword != confirmPassword)
        {
            Console.WriteLine("Passwords do not match.");
            return;
        }
        confirmedPassword = newPassword;
    }

    Console.Write($"New role (admin/user) [{displayRole}]: ");
    var newRoleInput = Console.ReadLine()?.Trim().ToLower() ?? "";

    // Check if any changes were made
    var emailChanged = !string.IsNullOrEmpty(newEmail) && newEmail != currentEmail;
    var passwordChanged = !string.IsNullOrEmpty(confirmedPassword);
    var roleChanged = !string.IsNullOrEmpty(newRoleInput) && newRoleInput != displayRole;

    if (!emailChanged && !passwordChanged && !roleChanged)
    {
        Console.WriteLine("No changes made.");
        return;
    }

    // Apply changes
    var now = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");

    if (emailChanged)
    {
        var domain = newEmail.Contains('@') ? newEmail.Split('@')[1] : "example.com";
        user["email_addresses"] = new JArray
        {
            new JObject
            {
                ["address"] = newEmail,
                ["domain"] = domain
            }
        };
    }

    if (passwordChanged)
    {
        var hash = BCrypt.Net.BCrypt.HashPassword(confirmedPassword, 10);
        user["passwords"] = new JArray
        {
            new JObject
            {
                ["purpose"] = "generic",
                ["algorithm"] = "bcrypt",
                ["hash"] = hash,
                ["cost"] = 10,
                ["expired_at"] = "0001-01-01T00:00:00Z",
                ["created_at"] = now,
                ["disabled_at"] = "0001-01-01T00:00:00Z"
            }
        };
    }

    if (roleChanged)
    {
        var newRole = newRoleInput == "admin" ? "authp/admin" : "authp/user";
        user["roles"] = new JArray
        {
            new JObject
            {
                ["name"] = newRole,
                ["organization"] = "authp"
            }
        };
    }

    user["last_modified"] = now;
    db["revision"] = (int)db["revision"]! + 1;

    SaveDatabase(db);

    var changes = new List<string>();
    if (emailChanged) changes.Add("email");
    if (passwordChanged) changes.Add("password");
    if (roleChanged) changes.Add("role");

    Console.WriteLine($"User '{username}' updated successfully ({string.Join(", ", changes)}).");
    RestartCaddyIfRunning();
}

void ListUsers()
{
    if (!File.Exists(usersFile))
    {
        Console.WriteLine("No users.json found. Run 'init' first.");
        return;
    }

    var db = LoadDatabase();
    var users = (JArray)db["users"]!;

    Console.WriteLine($"Users ({users.Count}):");
    Console.WriteLine(new string('-', 60));
    Console.WriteLine($"{"Username",-20} {"Email",-30} {"Role",-10}");
    Console.WriteLine(new string('-', 60));

    foreach (var user in users)
    {
        var username = user["username"]?.ToString() ?? "";
        var email = user["email_addresses"]?[0]?["address"]?.ToString() ?? "";
        var role = user["roles"]?[0]?["name"]?.ToString() ?? "";

        // Skip placeholder users
        if (username == "admin" && user["passwords"]?[0]?["hash"]?.ToString() == "REPLACE_WITH_BCRYPT_HASH")
        {
            Console.WriteLine($"{username,-20} {email,-30} {"(template)",-10}");
            continue;
        }

        Console.WriteLine($"{username,-20} {email,-30} {role,-10}");
    }
}

void HashPassword()
{
    Console.Write("Password to hash: ");
    var password = ReadPassword();
    Console.WriteLine();

    if (string.IsNullOrEmpty(password))
    {
        Console.WriteLine("Password is required.");
        return;
    }

    var hash = BCrypt.Net.BCrypt.HashPassword(password, 10);
    Console.WriteLine();
    Console.WriteLine("BCrypt hash:");
    Console.WriteLine(hash);
}

JObject LoadOrCreateDatabase()
{
    if (File.Exists(usersFile))
    {
        return LoadDatabase();
    }

    // Create from template
    File.Copy(usersExample, usersFile, overwrite: true);
    return LoadDatabase();
}

JObject LoadDatabase()
{
    var json = File.ReadAllText(usersFile);
    return JObject.Parse(json);
}

void SaveDatabase(JObject db)
{
    var json = JsonConvert.SerializeObject(db, Formatting.Indented);
    File.WriteAllText(usersFile, json);
}

string ReadPassword()
{
    var password = "";
    while (true)
    {
        var key = Console.ReadKey(intercept: true);
        if (key.Key == ConsoleKey.Enter)
            break;
        if (key.Key == ConsoleKey.Backspace && password.Length > 0)
        {
            password = password[..^1];
            Console.Write("\b \b");
        }
        else if (!char.IsControl(key.KeyChar))
        {
            password += key.KeyChar;
            Console.Write("*");
        }
    }
    return password;
}

void RestartCaddyIfRunning()
{
    var caddyDir = Path.Combine(repoRoot, "services", "90-caddy");

    // Check if Caddy container is running
    var psResult = ProcessRunner.RunInDir("docker", "compose ps -q caddy", caddyDir, printErrors: false);
    if (!psResult.Success || string.IsNullOrWhiteSpace(psResult.Output))
    {
        return; // Not running, no need to restart
    }

    Console.WriteLine("Restarting Caddy to apply changes...");
    var result = ProcessRunner.RunInDir("docker", "compose restart caddy", caddyDir);
    if (result.Success)
    {
        Console.WriteLine("Caddy restarted successfully.");
    }
}
