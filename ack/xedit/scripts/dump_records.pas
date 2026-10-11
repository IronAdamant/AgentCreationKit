{
  AgentCreationKit: dump chosen records from any loaded plugin (masters included) as indented text with every
  field decoded, to learn xEdit field paths before editing. Read-only.
  Parameters: RECORDS (editor IDs separated by commas).
}
unit ACKDumpRecords;

const
  OutDir = '{{OUT}}';
  RecordList = '{{RECORDS}}';

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

function FindAny(edid: string): IInterface;
var
  i, j: integer;
  f, g: IInterface;
begin
  Result := nil;
  for i := FileCount - 1 downto 0 do begin
    f := FileByIndex(i);
    for j := 0 to ElementCount(f) - 1 do begin
      g := ElementByIndex(f, j);
      if Signature(g) = 'GRUP' then begin
        Result := MainRecordByEditorID(g, edid);
        if Assigned(Result) then
          Exit;
      end;
    end;
  end;
  // placed references live inside cell groups, out of MainRecordByEditorID's reach: scan every record
  for i := FileCount - 1 downto 0 do begin
    f := FileByIndex(i);
    for j := 0 to RecordCount(f) - 1 do begin
      g := RecordByIndex(f, j);
      if SameText(EditorID(g), edid) then begin
        Result := g;
        Exit;
      end;
    end;
  end;
end;

function Initialize: integer;
var
  i: integer;
  rec: IInterface;
  names, sl, done: TStringList;
begin
  names := TStringList.Create;
  names.Delimiter := ',';
  names.StrictDelimiter := True;
  names.DelimitedText := RecordList;
  sl := TStringList.Create;
  for i := 0 to names.Count - 1 do begin
    rec := FindAny(Trim(names[i]));
    sl.Add('==== ' + Trim(names[i]));
    if Assigned(rec) then
      DumpElement(sl, 0, rec)
    else
      sl.Add('NOT FOUND');
  end;
  sl.SaveToFile(OutDir + 'records.txt');
  done := TStringList.Create;
  done.Add('ok');
  done.SaveToFile(OutDir + 'DONE.txt');
  done.Free;
  sl.Free;
  names.Free;
  Result := 0;
end;

end.
