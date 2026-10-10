{
  AgentCreationKit: remove masters the target plugin no longer references.
  EDITS the plugin - run with save enabled. Writes masters.txt and DONE.txt.
}
unit ACKCleanMasters;

const
  TargetFile = '{{TARGET}}';
  OutDir = '{{OUT}}';

function MasterList(f: IInterface): string;
var
  i: integer;
begin
  Result := '';
  for i := 0 to MasterCount(f) - 1 do
    Result := Result + GetFileName(MasterByIndex(f, i)) + '; ';
end;

function Initialize: integer;
var
  i: integer;
  f: IInterface;
  sl: TStringList;
begin
  sl := TStringList.Create;
  for i := 0 to FileCount - 1 do begin
    f := FileByIndex(i);
    if GetFileName(f) <> TargetFile then
      Continue;
    sl.Add('Before: ' + MasterList(f));
    CleanMasters(f);
    sl.Add('After:  ' + MasterList(f));
  end;
  sl.SaveToFile(OutDir + 'masters.txt');
  sl.Clear;
  sl.Add('ok');
  sl.SaveToFile(OutDir + 'DONE.txt');
  sl.Free;
  Result := 0;
end;

end.
