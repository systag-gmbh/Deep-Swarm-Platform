#!/usr/bin/env -S dotnet run
// v2 - streaming output, deadlock fix
#:project lib/StackLib.csproj

using StackLib;

var repoRoot = Environment.CurrentDirectory;
var config = ConfigLoader.LoadConfig(repoRoot);
var envVars = ConfigLoader.BuildEnvironment(repoRoot, config);

Console.WriteLine($"Project: {config.ProjectName}");
Console.WriteLine($"Data path: {config.DataPath}");
Console.WriteLine($"Services: {string.Join(", ", config.Services)}");
Console.WriteLine();

// Ensure networks exist
DockerHelpers.EnsureNetworks(config);
Console.WriteLine();

// Start each service
foreach (var service in ServiceManager.GetServicesAscending(repoRoot, config))
{
    if (!service.ComposeFileExists)
    {
        Console.WriteLine($"✗ {service.Name} - docker-compose.yml not found");
        continue;
    }

    Console.WriteLine($"▶ Starting {service.Name}...");

    if (service.HasOverride)
    {
        Console.WriteLine($"  Using override: overrides/{service.Name}.override.yml");
    }

    var composeArgs = DockerHelpers.BuildComposeArgs(config.ProjectName, service.OverrideFile);
    composeArgs += service.HasDockerfile ? " up -d --build" : " up -d";

    var result = ProcessRunner.RunStreaming("docker", composeArgs, service.ServiceDir, envVars);

    if (result.Success)
    {
        Console.WriteLine($"✓ {service.Name}");
    }
    else
    {
        var reason = result.Error == "Process timed out" ? "timed out" : "failed";
        Console.WriteLine($"✗ {service.Name} - {reason}");
    }
    Console.WriteLine();
}

// Generate landing page
Console.WriteLine("Generating landing page...");
var landingResult = ProcessRunner.Run("dotnet", $"run {Path.Combine(repoRoot, "scripts", "generate-landing.cs")}");
if (!landingResult.Success)
{
    Console.WriteLine("✗ Failed to generate landing page");
}
