    // 检测上升沿: IN=TRUE且上一周期IN=FALSE
    Q := IN AND NOT LastIN;
    LastIN := IN;
