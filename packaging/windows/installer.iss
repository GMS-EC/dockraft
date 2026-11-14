#ifndef MyAppVersion
  #define MyAppVersion "1.6.0"
  #define ChangelogPath AddBackslash(SourcePath) + "..\..\CHANGELOG.md"
  #if FileExists(ChangelogPath)
    #define ChangelogHandle FileOpen(ChangelogPath)
    #if ChangelogHandle
      #sub ReadChangelogLine
        #define LineText FileRead(ChangelogHandle)
        #if Pos("## [", LineText) == 1
          #define EndBrk Pos("]", LineText)
          #if EndBrk > 4
            #define MyAppVersion Copy(LineText, 5, EndBrk - 5)
          #endif
        #endif
      #endsub
      #for {0; !FileEof(ChangelogHandle) && (MyAppVersion == "1.6.0"); 0} ReadChangelogLine
      #expr FileClose(ChangelogHandle)
    #endif
  #endif
#endif

[Setup]
AppId={{7D5E8B3A-4C9E-4F12-9B2A-8C1F4A9E1500}
AppName=Dockraft
AppVersion={#MyAppVersion}
AppPublisher=Marcus Mayorga (GMS-EC)
AppPublisherURL=https://gmsec.cc
AppSupportURL=https://github.com/GMS-EC/dockraft
VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany=Marcus Mayorga (GMS-EC)
VersionInfoDescription=Dockraft Setup
VersionInfoCopyright=Copyright (C) Marcus Mayorga (GMS-EC)
DefaultDirName={localappdata}\Programs\Dockraft
DefaultGroupName=Dockraft
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=Dockraft-Windows-Setup-{#MyAppVersion}
SetupIconFile=dockraft.ico
UninstallDisplayIcon={app}\Dockraft.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\dist\Dockraft\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Dockraft"; Filename: "{app}\Dockraft.exe"; IconFilename: "{app}\Dockraft.exe"
Name: "{group}\{cm:UninstallProgram,Dockraft}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Dockraft"; Filename: "{app}\Dockraft.exe"; IconFilename: "{app}\Dockraft.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Dockraft.exe"; Description: "{cm:LaunchProgram,Dockraft}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\.dockraft_root"
