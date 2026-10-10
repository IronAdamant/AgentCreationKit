{
  AgentCreationKit self-test: renames the target plugin's first GLOB record in memory.
  Run WITHOUT --save to prove read-only runs never write (the plugin must be unchanged afterwards).
}
unit ACKSelftestEdit;

const
  TargetFile = '{{TARGET}}';
  OutDir = '{{OUT}}';

function Initialize: integer;
var
  i, j: integer;
  f, r: IInterface;
  sl: TStringList;
begin
  sl := TStringList.Create;
  for i := 0 to FileCount - 1 do begin
    f := FileByIndex(i);
    if GetFileName(f) <> TargetFile then
      Continue;
    for j := 0 to RecordCount(f) - 1 do begin
      r := RecordByIndex(f, j);
      if Signature(r) = 'GLOB' then begin
        sl.Add('Renamed ' + EditorID(r));
        SetEditorID(r, EditorID(r) + '_ACKSELFTEST');
        Break;
      end;
    end;
  end;
  sl.SaveToFile(OutDir + 'selftest.txt');
  sl.Clear;
  sl.Add('ok');
  sl.SaveToFile(OutDir + 'DONE.txt');
  sl.Free;
  Result := 0;
end;

end.
