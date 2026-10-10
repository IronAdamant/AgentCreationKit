{
  AgentCreationKit: run xEdit's Check() over every record in the target plugin.
  Read-only. Writes errors.txt and DONE.txt to the output folder.
}
unit ACKCheckErrors;

const
  TargetFile = '{{TARGET}}';
  OutDir = '{{OUT}}';

var
  sl: TStringList;

function CheckForErrors(aIndent: Integer; aElement: IInterface): Boolean;
var
  Error: string;
  i: Integer;
begin
  Error := Check(aElement);
  Result := Error <> '';
  if Result then
    sl.Add(StringOfChar(' ', aIndent * 2) + Name(aElement) + ' -> ' + Error);
  for i := ElementCount(aElement) - 1 downto 0 do
    Result := CheckForErrors(aIndent + 1, ElementByIndex(aElement, i)) or Result;
  if Result and (Error = '') and (aIndent = 0) then
    sl.Add('^^^ in ' + Name(aElement));
end;

function Initialize: integer;
var
  i, j, n: integer;
  f: IInterface;
  done: TStringList;
begin
  sl := TStringList.Create;
  n := 0;
  for i := 0 to FileCount - 1 do begin
    f := FileByIndex(i);
    if GetFileName(f) = TargetFile then begin
      for j := 0 to RecordCount(f) - 1 do
        if CheckForErrors(0, RecordByIndex(f, j)) then
          Inc(n);
      sl.Insert(0, Format('Checked %d records, %d with errors', [RecordCount(f), n]));
    end;
  end;
  if sl.Count = 0 then
    sl.Add('Target plugin not loaded');
  sl.SaveToFile(OutDir + 'errors.txt');
  sl.Free;
  done := TStringList.Create;
  done.Add('ok');
  done.SaveToFile(OutDir + 'DONE.txt');
  done.Free;
  Result := 0;
end;

end.
