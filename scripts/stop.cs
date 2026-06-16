#!/usr/bin/env -S dotnet run
// v2 - deadlock fix
#:project lib/StackLib.csproj

using StackLib;

var repoRoot = Environment.CurrentDirectory;
var config = ConfigLoader.LoadConfig(repoRoot);
var envVars = ConfigLoader.BuildEnvironment(repoRoot, config);

Console.WriteLine($"Project: {config.ProjectName}");
Console.WriteLine("Stopping services in reverse order...");
Console.WriteLine();

// Stop each service in reverse order (dependencies last)
foreach (var service in ServiceManager.GetServicesDescending(repoRoot, config))
{
    if (!service.ComposeFileExists)
    {
        Console.WriteLine($"✗ {service.Name} - docker-compose.yml not found");
        continue;
    }

    Console.WriteLine($"■ Stopping {service.Name}...");

    var composeArgs = DockerHelpers.BuildComposeArgs(config.ProjectName, service.OverrideFile);
    composeArgs += " down";

    var result = ProcessRunner.RunInDir("docker", composeArgs, service.ServiceDir, envVars);

    if (result.Success)
    {
        Console.WriteLine($"✓ {service.Name} stopped");
    }
    else
    {
        Console.WriteLine($"✗ {service.Name} - failed to stop");
    }
    Console.WriteLine();
}
