#!/usr/bin/env -S dotnet run
#:package YamlDotNet@16.3.0

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;

// Determine paths (use current directory for file-based scripts)
var repoRoot = Environment.CurrentDirectory;
var yamlPath = Path.Combine(repoRoot, "landing.yaml");
var versionPath = Path.Combine(repoRoot, "VERSION");
var outputPath = Path.Combine(repoRoot, "services", "90-caddy", "static", "index.html");

// Check if YAML file exists
if (!File.Exists(yamlPath))
{
    Console.WriteLine($"✗ landing.yaml not found at {yamlPath}");
    Environment.Exit(1);
}

// Parse YAML
var deserializer = new DeserializerBuilder()
    .WithNamingConvention(CamelCaseNamingConvention.Instance)
    .Build();

var yamlContent = File.ReadAllText(yamlPath);
var config = deserializer.Deserialize<LandingConfig>(yamlContent);

// Read version info
var versionInfo = GetVersionInfo(versionPath, repoRoot);

// Generate HTML
var html = GenerateHtml(config, versionInfo);

// Ensure output directory exists
var outputDir = Path.GetDirectoryName(outputPath);
if (!Directory.Exists(outputDir))
{
    Directory.CreateDirectory(outputDir!);
}

// Write HTML
File.WriteAllText(outputPath, html);
Console.WriteLine($"✓ Generated {outputPath}");

// Helper methods (must be before class declarations)
static string GenerateHtml(LandingConfig config, string versionInfo)
{
    var sb = new StringBuilder();

    sb.AppendLine("<!DOCTYPE html>");
    sb.AppendLine("<html lang=\"de\">");
    sb.AppendLine("<head>");
    sb.AppendLine("    <meta charset=\"UTF-8\">");
    sb.AppendLine("    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">");
    sb.AppendLine($"    <title>{EscapeHtml(config.Title)}</title>");
    sb.AppendLine("    <link rel=\"icon\" href=\"data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAzMiAzMiI+PGRlZnM+PGxpbmVhckdyYWRpZW50IGlkPSJnIiB4MT0iMCUiIHkxPSIwJSIgeDI9IjEwMCUiIHkyPSIxMDAlIj48c3RvcCBvZmZzZXQ9IjAlIiBzdG9wLWNvbG9yPSIjNjY3ZWVhIi8+PHN0b3Agb2Zmc2V0PSIxMDAlIiBzdG9wLWNvbG9yPSIjNzY0YmEyIi8+PC9saW5lYXJHcmFkaWVudD48L2RlZnM+PGNpcmNsZSBjeD0iMTYiIGN5PSIxNiIgcj0iNSIgZmlsbD0idXJsKCNnKSIvPjxjaXJjbGUgY3g9IjYiIGN5PSIxMCIgcj0iMyIgZmlsbD0idXJsKCNnKSIgb3BhY2l0eT0iMC44Ii8+PGNpcmNsZSBjeD0iMjYiIGN5PSIxMCIgcj0iMyIgZmlsbD0idXJsKCNnKSIgb3BhY2l0eT0iMC44Ii8+PGNpcmNsZSBjeD0iNiIgY3k9IjIyIiByPSIzIiBmaWxsPSJ1cmwoI2cpIiBvcGFjaXR5PSIwLjgiLz48Y2lyY2xlIGN4PSIyNiIgY3k9IjIyIiByPSIzIiBmaWxsPSJ1cmwoI2cpIiBvcGFjaXR5PSIwLjgiLz48Y2lyY2xlIGN4PSIxNiIgY3k9IjQiIHI9IjIuNSIgZmlsbD0idXJsKCNnKSIgb3BhY2l0eT0iMC42Ii8+PGNpcmNsZSBjeD0iMTYiIGN5PSIyOCIgcj0iMi41IiBmaWxsPSJ1cmwoI2cpIiBvcGFjaXR5PSIwLjYiLz48L3N2Zz4K\">");
    sb.AppendLine("    <style>");
    sb.AppendLine(GetCss());
    sb.AppendLine("    </style>");
    sb.AppendLine("</head>");
    sb.AppendLine("<body>");
    sb.AppendLine("    <svg class=\"background-icon\" xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 32 32\"><defs><linearGradient id=\"bg\" x1=\"0%\" y1=\"0%\" x2=\"100%\" y2=\"100%\"><stop offset=\"0%\" stop-color=\"#667eea\"/><stop offset=\"100%\" stop-color=\"#764ba2\"/></linearGradient></defs><circle cx=\"16\" cy=\"16\" r=\"5\" fill=\"url(#bg)\"/><circle cx=\"6\" cy=\"10\" r=\"3\" fill=\"url(#bg)\" opacity=\"0.8\"/><circle cx=\"26\" cy=\"10\" r=\"3\" fill=\"url(#bg)\" opacity=\"0.8\"/><circle cx=\"6\" cy=\"22\" r=\"3\" fill=\"url(#bg)\" opacity=\"0.8\"/><circle cx=\"26\" cy=\"22\" r=\"3\" fill=\"url(#bg)\" opacity=\"0.8\"/><circle cx=\"16\" cy=\"4\" r=\"2.5\" fill=\"url(#bg)\" opacity=\"0.6\"/><circle cx=\"16\" cy=\"28\" r=\"2.5\" fill=\"url(#bg)\" opacity=\"0.6\"/></svg>");
    sb.AppendLine("    <div class=\"container\">");
    sb.AppendLine("        <header>");
    sb.AppendLine($"            <h1>{EscapeHtml(config.Title)}</h1>");
    sb.AppendLine("        </header>");
    sb.AppendLine("        <div class=\"grid\">");

    foreach (var group in config.Groups)
    {
        sb.AppendLine("            <div class=\"card\">");
        sb.AppendLine($"                <h2>{EscapeHtml(group.Name)}</h2>");
        sb.AppendLine("                <div class=\"links\">");

        foreach (var link in group.Links)
        {
            sb.AppendLine($"                    <a href=\"{EscapeHtml(link.Url)}\" rel=\"noopener noreferrer\" target=\"_blank\">");
            sb.AppendLine($"                        <div class=\"icon\">{EscapeHtml(link.Icon)}</div>");
            sb.AppendLine("                        <div class=\"text\">");
            sb.AppendLine($"                            <div class=\"name\">{EscapeHtml(link.Name)}</div>");
            sb.AppendLine($"                            <div class=\"desc\">{EscapeHtml(link.Description)}</div>");
            sb.AppendLine("                        </div>");
            sb.AppendLine("                        <span class=\"arrow\">&rarr;</span>");
            sb.AppendLine("                    </a>");
        }

        sb.AppendLine("                </div>");

        if (group.ShowVersion && !string.IsNullOrEmpty(versionInfo))
        {
            sb.AppendLine($"                <div class=\"version\">{EscapeHtml(versionInfo)}</div>");
        }

        sb.AppendLine("            </div>");
    }

    sb.AppendLine("        </div>");
    sb.AppendLine("    </div>");
    sb.AppendLine("</body>");
    sb.AppendLine("</html>");

    return sb.ToString();
}

static string EscapeHtml(string text)
{
    return text
        .Replace("&", "&amp;")
        .Replace("<", "&lt;")
        .Replace(">", "&gt;")
        .Replace("\"", "&quot;");
}

static string GetVersionInfo(string versionPath, string repoRoot)
{
    // Read version from VERSION file
    var version = "0.0.0";
    if (File.Exists(versionPath))
    {
        version = File.ReadAllText(versionPath).Trim();
    }

    // Get short git commit hash
    var commitHash = GetGitCommitHash(repoRoot);

    // Generate timestamp in German format (local time)
    var timestamp = DateTime.Now.ToString("dd.MM.yy HH:mm");

    return $"v{version} ({commitHash}) • Built {timestamp}";
}

static string GetGitCommitHash(string repoRoot)
{
    try
    {
        var psi = new ProcessStartInfo
        {
            FileName = "git",
            Arguments = "rev-parse --short HEAD",
            WorkingDirectory = repoRoot,
            RedirectStandardOutput = true,
            UseShellExecute = false
        };

        using var process = Process.Start(psi);
        var output = process!.StandardOutput.ReadToEnd().Trim();
        process.WaitForExit();

        return process.ExitCode == 0 ? output : "unknown";
    }
    catch
    {
        return "unknown";
    }
}

static string GetCss()
{
    return @"        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            color: #e4e4e4;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 2rem;
        }

        .container {
            max-width: 900px;
            width: 100%;
        }

        header {
            text-align: center;
            margin-bottom: 3rem;
        }

        h1 {
            font-size: 2.5rem;
            font-weight: 300;
            letter-spacing: 0.1em;
            color: #fff;
            text-shadow: 0 2px 10px rgba(0, 0, 0, 0.3);
        }

        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 2rem;
        }

        @media (max-width: 700px) {
            .grid {
                grid-template-columns: 1fr;
            }
        }

        .card {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            padding: 1.5rem;
            backdrop-filter: blur(10px);
        }

        .card h2 {
            font-size: 1.1rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.15em;
            color: #94a3b8;
            margin-bottom: 1.25rem;
            padding-bottom: 0.75rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }

        .links {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }

        .links a {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.875rem 1rem;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 10px;
            color: #e4e4e4;
            text-decoration: none;
            transition: all 0.2s ease;
        }

        .links a:hover {
            background: rgba(255, 255, 255, 0.1);
            border-color: rgba(255, 255, 255, 0.15);
            transform: translateX(4px);
        }

        .links a .icon {
            width: 32px;
            height: 32px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1rem;
            flex-shrink: 0;
        }

        .links a .text {
            flex: 1;
        }

        .links a .name {
            font-weight: 500;
            font-size: 0.95rem;
        }

        .links a .desc {
            font-size: 0.75rem;
            color: #94a3b8;
            margin-top: 0.125rem;
        }

        .links a .arrow {
            color: #64748b;
            font-size: 1.25rem;
            transition: transform 0.2s ease;
        }

        .links a:hover .arrow {
            transform: translateX(4px);
        }


        .background-icon {
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 60vmin;
            height: 60vmin;
            opacity: 0.15;
            pointer-events: none;
            z-index: 0;
        }

        .container {
            position: relative;
            z-index: 1;
        }

        .card .version {
            margin-top: 1rem;
            padding-top: 0.75rem;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
            color: #64748b;
            font-size: 0.7rem;
            letter-spacing: 0.05em;
            text-align: center;
        }";
}

// Classes for YAML deserialization (must come after top-level statements)
class LandingConfig
{
    public string Title { get; set; } = "";
    public List<Group> Groups { get; set; } = new();
}

class Group
{
    public string Name { get; set; } = "";
    public bool ShowVersion { get; set; } = false;
    public List<Link> Links { get; set; } = new();
}

class Link
{
    public string Name { get; set; } = "";
    public string Url { get; set; } = "";
    public string Icon { get; set; } = "";
    public string Description { get; set; } = "";
}
