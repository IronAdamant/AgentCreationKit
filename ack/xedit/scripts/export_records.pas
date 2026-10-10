{
  AgentCreationKit: export every record in the target plugin as indented text,
  one file per record signature, with all fields decoded. Read-only.
}
unit ACKExportRecords;

const
  TargetFile = '{{TARGET}}';
  OutDir = '{{OUT}}';

procedure DumpElement(sl: TStringList; aIndent: Integer; e: IInterface);
var
  i: Integer;
  v: string;
begin
  v := GetEditValue(e);
  if v <> '' then
    sl.Add(StringOfChar(' ', aIndent * 2) + Name(e) + ' = ' + v)
  else
    sl.Add(StringOfChar(' ', aIndent * 2) + Name(e));
  for i := 0 to ElementCount(e) - 1 do
    DumpElement(sl, aIndent + 1, ElementByIndex(e, i));
end;

function Initialize: integer;
var
  i, j, k: integer;
  f, rec: IInterface;
  sig: string;
  sigs, sl, done: TStringList;
begin
  sigs := TStringList.Create;
  for i := 0 to FileCount - 1 do begin
    f := FileByIndex(i);
    if GetFileName(f) <> TargetFile then
      Continue;
    for j := 0 to RecordCount(f) - 1 do begin
      rec := RecordByIndex(f, j);
      sig := Signature(rec);
      k := sigs.IndexOf(sig);
      if k < 0 then
        k := sigs.AddObject(sig, TStringList.Create);
      sl := TStringList(sigs.Objects[k]);
      sl.Add('==== ' + sig + ' ' + IntToHex(FormID(rec), 8) + ' ' + EditorID(rec));
      DumpElement(sl, 0, rec);
      sl.Add('');
    end;
  end;
  for k := 0 to sigs.Count - 1 do begin
    sl := TStringList(sigs.Objects[k]);
    sl.SaveToFile(OutDir + sigs[k] + '.txt');
    sl.Free;
  end;
  done := TStringList.Create;
  done.Add(IntToStr(sigs.Count) + ' signatures exported');
  done.SaveToFile(OutDir + 'DONE.txt');
  done.Free;
  sigs.Free;
  Result := 0;
end;

end.
