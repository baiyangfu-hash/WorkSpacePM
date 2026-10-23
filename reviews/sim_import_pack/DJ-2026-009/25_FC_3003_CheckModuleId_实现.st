    FC_3003_CheckModuleId := ID_OK;
    IF LEN(i_sModuleId) = 0 THEN
        FC_3003_CheckModuleId := FC_3003_CheckModuleId OR ID_ERR_EMPTY;
    END_IF;
