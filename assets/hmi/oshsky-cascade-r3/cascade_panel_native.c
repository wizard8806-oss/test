/* SKTool 7.1, Oshsky r3. Included after cascade_countdown.c in AlarmSound. */
static void CascadePanel(IN *p)
{
    static OshskyCountdownState state;
    OshskyCountdownOutput value;
    unsigned short words[6];
    unsigned short i;
    unsigned short sec=InfoBCD(LocalWord[60000]), min=InfoBCD(LocalWord[60001]);
    unsigned short hour=InfoBCD(LocalWord[60002]), day=InfoBCD(LocalWord[60003]);
    unsigned short month=InfoBCD(LocalWord[60004]), year=InfoBCD(LocalWord[60005]);
    unsigned short valid=LocalBit[60107] && MapVersion==32u && OshContract==27110u
        && sec<60u && min<60u && hour<24u && day>0u && day<32u
        && month>0u && month<13u && year>=2000u && year<2100u;
    unsigned long days=0ul,now=0ul;
    if(valid) {
        unsigned long y=year-(month<=2u);
        unsigned long m=month+(month<=2u?9:-3);
        days=365ul*(y-1999ul)+y/4ul-1999ul/4ul+(153ul*m+2ul)/5ul+day-1ul;
        now=((days*24ul+hour)*60ul+min)*60ul+sec;
    }
    for(i=0u;i<6u;++i) words[i]=(unsigned short)CascadeBlock[i];
    OshskyCountdown(&state,words,valid,
        CascadeMode>=10u && CascadeMode<=12u && AlarmWords[2]==0u,now,&value);
    LocalBit[2110]=valid && state.initialized && state.moving;
    LocalBit[2111]=value.action==1u;
    LocalBit[2112]=value.action==2u;
    LocalWord[54010]=value.pump;
    LocalWord[54011]=value.seconds;
    LocalWord[54012]=value.seconds>=1000u?4u:(value.seconds>=100u?3u:(value.seconds>=10u?2u:1u));
}
